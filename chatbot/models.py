from django.db import models
from django.conf import settings
from django.utils import timezone


class APIRequestLog(models.Model):
    STATUS_CHOICES = [
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('rate_limited', 'Rate Limited (429)'),
    ]

    USAGE_SOURCE_CHOICES = [
        ('api_reported', 'API Reported'),
        ('estimated', 'Estimated'),
        ('unavailable', 'Unavailable'),
    ]

    ESTIMATE_CHOICES = [
        ('actual', 'Actual (API Verified)'),
        ('estimated', 'Estimated'),
    ]

    model_name = models.CharField(max_length=120, db_index=True)
    endpoint = models.CharField(max_length=200, default='/openai/v1/chat/completions')
    input_tokens = models.PositiveIntegerField(default=0)
    output_tokens = models.PositiveIntegerField(default=0)
    total_tokens = models.PositiveIntegerField(default=0)
    request_status = models.CharField(max_length=25, choices=STATUS_CHOICES, default='success', db_index=True)
    error_message = models.TextField(blank=True, default='')
    response_time_ms = models.FloatField(default=0.0, help_text='Latency in milliseconds')
    request_timestamp = models.DateTimeField(default=timezone.now, db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='groq_api_logs'
    )
    usage_source = models.CharField(max_length=40, choices=USAGE_SOURCE_CHOICES, default='api_reported')
    estimated_or_actual = models.CharField(max_length=20, choices=ESTIMATE_CHOICES, default='actual')
    audio_duration_seconds = models.FloatField(default=0.0, help_text='For speech-to-text calls')

    class Meta:
        ordering = ['-request_timestamp']
        indexes = [
            models.Index(fields=['request_timestamp', 'model_name']),
            models.Index(fields=['request_status', 'request_timestamp']),
        ]

    def __str__(self):
        return f"{self.request_timestamp:%Y-%m-%d %H:%M} | {self.model_name} | {self.total_tokens} tokens | {self.request_status}"


class ModelQuotaConfig(models.Model):
    QUOTA_TYPE_CHOICES = [
        ('free_tier', 'Free Tier'),
        ('tier_1', 'Developer Tier 1'),
        ('pay_as_you_go', 'Pay As You Go'),
        ('custom', 'Custom Configured'),
    ]

    model_name = models.CharField(max_length=120, unique=True)
    requests_per_minute = models.PositiveIntegerField(null=True, blank=True, help_text='RPM limit (null = unknown)')
    requests_per_day = models.PositiveIntegerField(null=True, blank=True, help_text='RPD limit (null = unknown)')
    tokens_per_minute = models.PositiveIntegerField(null=True, blank=True, help_text='TPM limit (null = unknown)')
    tokens_per_day = models.PositiveIntegerField(null=True, blank=True, help_text='TPD limit (null = unknown)')
    quota_type = models.CharField(max_length=40, choices=QUOTA_TYPE_CHOICES, default='free_tier')
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['model_name']

    def __str__(self):
        return f"{self.model_name} (TPD: {self.tokens_per_day or 'Unknown'})"


class DailyUsageSummary(models.Model):
    date = models.DateField(db_index=True)
    model_name = models.CharField(max_length=120, db_index=True)
    total_requests = models.PositiveIntegerField(default=0)
    successful_requests = models.PositiveIntegerField(default=0)
    failed_requests = models.PositiveIntegerField(default=0)
    input_tokens = models.PositiveIntegerField(default=0)
    output_tokens = models.PositiveIntegerField(default=0)
    total_tokens = models.PositiveIntegerField(default=0)
    audio_duration_seconds = models.FloatField(default=0.0)

    class Meta:
        ordering = ['-date', 'model_name']
        unique_together = ['date', 'model_name']

    def __str__(self):
        return f"{self.date} | {self.model_name} | Req: {self.total_requests} | Tok: {self.total_tokens}"


class RateLimitSnapshot(models.Model):
    model_name = models.CharField(max_length=120, db_index=True)
    captured_at = models.DateTimeField(default=timezone.now, db_index=True)
    limit_requests = models.PositiveIntegerField(null=True, blank=True)
    remaining_requests = models.PositiveIntegerField(null=True, blank=True)
    limit_tokens = models.PositiveIntegerField(null=True, blank=True)
    remaining_tokens = models.PositiveIntegerField(null=True, blank=True)
    reset_requests = models.CharField(max_length=50, blank=True, default='')
    reset_tokens = models.CharField(max_length=50, blank=True, default='')
    source = models.CharField(max_length=80, default='api_header')

    class Meta:
        ordering = ['-captured_at']

    def __str__(self):
        return f"{self.model_name} at {self.captured_at:%Y-%m-%d %H:%M:%S} (Rem Tokens: {self.remaining_tokens})"


class ChatConversation(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True, related_name='swecha_chats')
    session_id = models.CharField(max_length=120, db_index=True, blank=True)
    title = models.CharField(max_length=200, default='New Chat')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f"{self.title} ({self.user.username if self.user else self.session_id})"


class ChatMessage(models.Model):
    ROLE_CHOICES = [
        ('user', 'User'),
        ('assistant', 'Assistant'),
        ('system', 'System'),
    ]

    conversation = models.ForeignKey(ChatConversation, on_delete=models.CASCADE, related_name='messages')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"[{self.role}] {self.content[:40]}"
