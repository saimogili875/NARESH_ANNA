from datetime import date, timedelta
from unittest.mock import MagicMock, patch
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.utils import timezone
from .models import (
    APIRequestLog,
    ModelQuotaConfig,
    DailyUsageSummary,
    RateLimitSnapshot,
)
from .services import (
    log_and_aggregate_request,
    get_token_analytics_data,
    seed_default_quotas,
    ask_swecha,
)

User = get_user_model()


class GroqTokenTrackerTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testadmin', password='testpassword123', role='admin')
        self.client = Client()
        self.client.force_login(self.user)

        # Seed Model Quotas
        self.quota = ModelQuotaConfig.objects.create(
            model_name='qwen/qwen3.8-27b',
            requests_per_minute=30,
            requests_per_day=14400,
            tokens_per_minute=6000,
            tokens_per_day=500000,
            quota_type='free_tier',
            is_active=True
        )

    def test_token_usage_extraction_and_aggregation(self):
        """Test logging request and atomic daily aggregation without double counting."""
        log = log_and_aggregate_request(
            model_name='qwen/qwen3.8-27b',
            endpoint='/openai/v1/chat/completions',
            input_tokens=150,
            output_tokens=75,
            total_tokens=225,
            request_status='success',
            response_time_ms=450.0,
            user=self.user,
            usage_source='api_reported',
            estimated_or_actual='actual'
        )

        self.assertEqual(log.total_tokens, 225)
        self.assertEqual(log.input_tokens, 150)
        self.assertEqual(log.output_tokens, 75)
        self.assertEqual(log.usage_source, 'api_reported')
        self.assertEqual(log.estimated_or_actual, 'actual')

        # Check atomic daily summary
        summary = DailyUsageSummary.objects.get(date=date.today(), model_name='qwen/qwen3.8-27b')
        self.assertEqual(summary.total_requests, 1)
        self.assertEqual(summary.successful_requests, 1)
        self.assertEqual(summary.failed_requests, 0)
        self.assertEqual(summary.total_tokens, 225)

        # Add a second request on the same day and ensure aggregate increments without duplicating
        log_and_aggregate_request(
            model_name='qwen/qwen3.8-27b',
            input_tokens=50,
            output_tokens=50,
            total_tokens=100,
            request_status='success'
        )

        summary.refresh_from_db()
        self.assertEqual(summary.total_requests, 2)
        self.assertEqual(summary.total_tokens, 325)
        self.assertEqual(summary.input_tokens, 200)
        self.assertEqual(summary.output_tokens, 125)

    def test_missing_usage_metadata_handling(self):
        """When usage metadata is missing from API, label as unavailable and do not invent tokens."""
        log = log_and_aggregate_request(
            model_name='qwen/qwen3.8-27b',
            input_tokens=0,
            output_tokens=0,
            total_tokens=0,
            request_status='success',
            usage_source='unavailable',
            estimated_or_actual='estimated'
        )
        self.assertEqual(log.total_tokens, 0)
        self.assertEqual(log.usage_source, 'unavailable')
        self.assertEqual(log.estimated_or_actual, 'estimated')

    def test_failed_and_rate_limit_request_logging(self):
        """Failed requests must be recorded with 0 tokens and correct status without inventing tokens."""
        log = log_and_aggregate_request(
            model_name='qwen/qwen3.8-27b',
            input_tokens=0,
            output_tokens=0,
            total_tokens=0,
            request_status='rate_limited',
            error_message='Error code: 429 - Rate limit reached',
            response_time_ms=120.0,
            usage_source='unavailable'
        )

        self.assertEqual(log.request_status, 'rate_limited')
        self.assertEqual(log.total_tokens, 0)
        self.assertEqual(log.usage_source, 'unavailable')

        summary = DailyUsageSummary.objects.get(date=date.today(), model_name='qwen/qwen3.8-27b')
        self.assertEqual(summary.failed_requests, 1)

    def test_rate_limit_snapshot_capture(self):
        """Header rate limit snapshot should be saved accurately."""
        headers = {
            'limit_requests': 30,
            'remaining_requests': 29,
            'limit_tokens': 6000,
            'remaining_tokens': 5800,
            'reset_requests': '2s',
            'reset_tokens': '1.2s'
        }
        log_and_aggregate_request(
            model_name='qwen/qwen3.8-27b',
            input_tokens=20,
            output_tokens=10,
            total_tokens=30,
            rate_limit_headers=headers
        )

        snap = RateLimitSnapshot.objects.filter(model_name='qwen/qwen3.8-27b').first()
        self.assertIsNotNone(snap)
        self.assertEqual(snap.remaining_tokens, 5800)
        self.assertEqual(snap.reset_requests, '2s')

    def test_quota_calculation_and_percentages(self):
        """Verify daily quota calculation, remaining tokens, and percentage math."""
        log_and_aggregate_request(
            model_name='qwen/qwen3.8-27b',
            input_tokens=30000,
            output_tokens=20000,
            total_tokens=50000
        )

        data = get_token_analytics_data(date_filter='today', model_filter='qwen/qwen3.8-27b')
        self.assertEqual(data['total_tokens'], 50000)
        self.assertEqual(data['remaining_daily_tokens'], 450000)
        self.assertEqual(data['daily_usage_pct'], 10.0)

    def test_unknown_and_zero_quota_limits(self):
        """Models with unspecified limits should return None rather than misleading 0% or unlimited."""
        ModelQuotaConfig.objects.create(
            model_name='custom/unspecified-model',
            tokens_per_day=None,
            is_active=True
        )

        log_and_aggregate_request(
            model_name='custom/unspecified-model',
            input_tokens=100,
            output_tokens=100,
            total_tokens=200
        )

        data = get_token_analytics_data(date_filter='today', model_filter='custom/unspecified-model')
        self.assertIsNone(data['remaining_daily_tokens'])
        self.assertIsNone(data['daily_usage_pct'])
        self.assertIn("unavailable", data['quota_label'].lower())

    def test_monthly_and_range_aggregation(self):
        """Test 'month' and date range filters."""
        log_and_aggregate_request(
            model_name='qwen/qwen3.8-27b',
            input_tokens=400,
            output_tokens=200,
            total_tokens=600
        )

        data_month = get_token_analytics_data(date_filter='month')
        self.assertGreaterEqual(data_month['total_tokens'], 600)
        self.assertGreaterEqual(data_month['total_requests'], 1)

    def test_authentication_and_authorization(self):
        """Unauthenticated requests must be redirected to login."""
        anon_client = Client()
        res = anon_client.get('/chatbot/monitor/')
        self.assertEqual(res.status_code, 302)
        self.assertIn('/login/', res['Location'])

    @patch('chatbot.services.get_groq_client')
    def test_mocked_groq_api_call(self, mock_client_func):
        """Mock Groq completions call to test end-to-end token tracking without consuming real quota."""
        mock_client = MagicMock()
        mock_client_func.return_value = mock_client

        mock_completion = MagicMock()
        mock_completion.choices = [MagicMock(message=MagicMock(content="Mocked response from Swecha."))]
        mock_completion.usage.prompt_tokens = 110
        mock_completion.usage.completion_tokens = 45
        mock_completion.usage.total_tokens = 155

        mock_raw_res = MagicMock()
        mock_raw_res.parse.return_value = mock_completion
        mock_raw_res.http_response.headers = {
            'x-ratelimit-remaining-tokens': '499000',
            'x-ratelimit-limit-tokens': '500000'
        }

        mock_client.chat.completions.with_raw_response.create.return_value = mock_raw_res

        result = ask_swecha("Test query", user=self.user)
        self.assertTrue(result['success'])
        self.assertEqual(result['response'], "Mocked response from Swecha.")
        self.assertEqual(result['tokens']['total'], 155)

        log = APIRequestLog.objects.filter(model_name='qwen/qwen3.8-27b').first()
        self.assertIsNotNone(log)
        self.assertEqual(log.total_tokens, 155)
        self.assertEqual(log.request_status, 'success')

    def test_dashboard_and_csv_export_views(self):
        """Test overview dashboard status code and CSV export generation."""
        res = self.client.get('/chatbot/monitor/')
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'GROQ USAGE MONITOR')

        csv_res = self.client.get('/chatbot/monitor/requests/export-csv/')
        self.assertEqual(csv_res.status_code, 200)
        self.assertEqual(csv_res['Content-Type'], 'text/csv')
        self.assertIn('attachment; filename=', csv_res['Content-Disposition'])
        content = csv_res.content.decode('utf-8')
        self.assertIn('Total Tokens', content)
        self.assertIn('Model', content)

    def test_speech_to_text_separate_accounting(self):
        """Speech to text must track duration seconds separately without corrupting token counts."""
        log = log_and_aggregate_request(
            model_name='whisper-large-v3',
            endpoint='/openai/v1/audio/transcriptions',
            input_tokens=0,
            output_tokens=0,
            total_tokens=0,
            audio_duration_seconds=42.5
        )
        self.assertEqual(log.audio_duration_seconds, 42.5)
        self.assertEqual(log.total_tokens, 0)

        res = self.client.get('/chatbot/monitor/speech-to-text/')
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, '42.5')
