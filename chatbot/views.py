import csv
import json
from datetime import datetime, date
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_POST, require_GET
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.conf import settings
from django.contrib import messages
from django.db.models import Sum, Avg, Count
from .models import (
    ChatConversation,
    ChatMessage,
    APIRequestLog,
    ModelQuotaConfig,
    DailyUsageSummary,
    RateLimitSnapshot,
)
from .services import (
    ask_swecha,
    get_token_analytics_data,
    seed_default_quotas,
    get_college_live_context,
)


def get_or_create_conversation(request, conversation_id=None):
    if not request.session.session_key:
        request.session.save()
    session_id = request.session.session_key

    if conversation_id:
        try:
            if request.user.is_authenticated:
                return ChatConversation.objects.get(id=conversation_id, user=request.user)
            else:
                return ChatConversation.objects.get(id=conversation_id, session_id=session_id)
        except ChatConversation.DoesNotExist:
            pass

    if request.user.is_authenticated:
        conv = ChatConversation.objects.filter(user=request.user).first()
        if not conv:
            conv = ChatConversation.objects.create(user=request.user, session_id=session_id, title='New Conversation')
        return conv
    else:
        conv = ChatConversation.objects.filter(session_id=session_id).first()
        if not conv:
            conv = ChatConversation.objects.create(session_id=session_id, title='New Conversation')
        return conv


@login_required
def chatbot_page(request):
    """Dedicated full-screen Swecha AI Assistant page with Lovable styling & sound effects."""
    conv = get_or_create_conversation(request)
    recent_conversations = []
    if request.user.is_authenticated:
        recent_conversations = ChatConversation.objects.filter(user=request.user)[:10]

    context = {
        'conversation': conv,
        'recent_conversations': recent_conversations,
        'chat_messages': conv.messages.all(),
        'page_title': 'Swecha AI Assistant',
        'sound_url': '/static/chatbot_sound.mp3',
    }
    return render(request, 'chatbot/index.html', context)


@csrf_exempt
@require_POST
def chat_api(request):
    """API endpoint for both the full-page view and the global floating widget."""
    try:
        data = json.loads(request.body.decode('utf-8'))
    except Exception:
        data = request.POST

    user_message = data.get('message', '').strip()
    if not user_message:
        return JsonResponse({'status': 'error', 'error': 'Message cannot be empty.'}, status=400)

    conv_id = data.get('conversation_id')
    conv = get_or_create_conversation(request, conv_id)

    # Fetch recent history
    history = []
    for m in conv.messages.all().order_by('created_at')[:10]:
        history.append({'role': m.role, 'content': m.content})

    # Save user message
    ChatMessage.objects.create(
        conversation=conv,
        role='user',
        content=user_message,
    )

    # Query Groq AI with automatic token accounting
    result = ask_swecha(
        user_message=user_message,
        history=history,
        user=request.user if request.user.is_authenticated else None,
    )

    bot_reply = result.get('response', '')

    # Save bot message
    ChatMessage.objects.create(
        conversation=conv,
        role='assistant',
        content=bot_reply,
    )

    # Update conversation title if default
    if conv.title in ['New Conversation', 'New Chat']:
        clean_title = (user_message[:35] + '...') if len(user_message) > 35 else user_message
        conv.title = clean_title
        conv.save(update_fields=['title', 'updated_at'])

    return JsonResponse({
        'status': 'ok',
        'reply': bot_reply,
        'model': result.get('model', 'Groq'),
        'tokens': result.get('tokens', {}),
        'latency_ms': result.get('latency_ms', 0),
        'conversation_id': conv.id,
        'conversation_title': conv.title,
    })


@csrf_exempt
@require_POST
def clear_history_api(request):
    conv_id = request.POST.get('conversation_id')
    if not conv_id:
        try:
            data = json.loads(request.body.decode('utf-8'))
            conv_id = data.get('conversation_id')
        except Exception:
            pass

    conv = get_or_create_conversation(request, conv_id)
    conv.messages.all().delete()
    conv.title = 'New Conversation'
    conv.save()

    return JsonResponse({'status': 'ok', 'message': 'Chat history cleared successfully.'})


@require_GET
def quick_stats_api(request):
    ctx = get_college_live_context(user=request.user if request.user.is_authenticated else None)
    return JsonResponse({'status': 'ok', 'context': ctx})


# ==============================================================================
# GROQ USAGE MONITOR & QUOTA DASHBOARD VIEWS
# ==============================================================================

@login_required
def monitor_dashboard(request):
    """
    Overview Dashboard:
    Displays 8 summary cards, 5 Chart.js visualizations, date & model filters.
    """
    seed_default_quotas()
    date_filter = request.GET.get('date_filter', 'today')
    model_filter = request.GET.get('model_filter', 'all')
    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date')

    start_date = None
    end_date = None
    if start_date_str and end_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        except ValueError:
            pass

    data = get_token_analytics_data(
        date_filter=date_filter,
        model_filter=model_filter,
        start_date=start_date,
        end_date=end_date
    )

    available_models = ModelQuotaConfig.objects.filter(is_active=True).values_list('model_name', flat=True)
    if not available_models:
        available_models = APIRequestLog.objects.values_list('model_name', flat=True).distinct()

    context = {
        'page_title': 'GROQ USAGE MONITOR',
        'subtitle': 'Monitor AI inference, tokens, requests, and quota consumption.',
        'analytics': data,
        'available_models': list(available_models),
        'active_tab': 'overview',
    }
    return render(request, 'chatbot/monitor/dashboard.html', context)


@login_required
def monitor_analytics(request):
    """Detailed token usage analytics and breakdown table."""
    date_filter = request.GET.get('date_filter', '7d')
    model_filter = request.GET.get('model_filter', 'all')
    data = get_token_analytics_data(date_filter=date_filter, model_filter=model_filter)

    daily_summaries = DailyUsageSummary.objects.all().order_by('-date')[:30]
    available_models = ModelQuotaConfig.objects.values_list('model_name', flat=True)

    context = {
        'page_title': 'Token Usage Analytics',
        'analytics': data,
        'daily_summaries': daily_summaries,
        'available_models': list(available_models),
        'active_tab': 'analytics',
    }
    return render(request, 'chatbot/monitor/analytics.html', context)


@login_required
def monitor_requests(request):
    """
    API Request History Page:
    Search, filter by model, status, date range, pagination, and CSV export.
    """
    qs = APIRequestLog.objects.all().order_by('-request_timestamp')

    search = request.GET.get('q', '').strip()
    if search:
        qs = qs.filter(model_name__icontains=search) | qs.filter(error_message__icontains=search)

    model_name = request.GET.get('model', '')
    if model_name and model_name != 'all':
        qs = qs.filter(model_name=model_name)

    status = request.GET.get('status', '')
    if status and status != 'all':
        qs = qs.filter(request_status=status)

    date_filter = request.GET.get('date', '')
    if date_filter:
        try:
            target_date = datetime.strptime(date_filter, '%Y-%m-%d').date()
            qs = qs.filter(request_timestamp__date=target_date)
        except ValueError:
            pass

    paginator = Paginator(qs, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    available_models = APIRequestLog.objects.values_list('model_name', flat=True).distinct()

    context = {
        'page_title': 'API Request History',
        'page_obj': page_obj,
        'search': search,
        'selected_model': model_name,
        'selected_status': status,
        'selected_date': date_filter,
        'available_models': list(available_models),
        'active_tab': 'requests',
    }
    return render(request, 'chatbot/monitor/requests.html', context)


@login_required
def monitor_export_csv(request):
    """Exports API request logs to CSV."""
    qs = APIRequestLog.objects.all().order_by('-request_timestamp')

    model_name = request.GET.get('model', '')
    if model_name and model_name != 'all':
        qs = qs.filter(model_name=model_name)

    status = request.GET.get('status', '')
    if status and status != 'all':
        qs = qs.filter(request_status=status)

    response = HttpResponse(content_type='text/csv')
    filename = f"groq_requests_{date.today().strftime('%Y%m%d')}.csv"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    writer = csv.writer(response)
    writer.writerow([
        'ID', 'Timestamp (UTC)', 'Model', 'Endpoint',
        'Input Tokens', 'Output Tokens', 'Total Tokens',
        'Status', 'Latency (ms)', 'Usage Source', 'Error Message'
    ])

    for row in qs[:2000]:
        writer.writerow([
            row.id,
            row.request_timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            row.model_name,
            row.endpoint,
            row.input_tokens,
            row.output_tokens,
            row.total_tokens,
            row.request_status,
            row.response_time_ms,
            row.usage_source,
            row.error_message.replace('\n', ' ') if row.error_message else ''
        ])

    return response


@login_required
def monitor_models(request):
    """Model comparison page with token efficiency, speed and error rate."""
    seed_default_quotas()
    models_data = []

    for cfg in ModelQuotaConfig.objects.all():
        logs = APIRequestLog.objects.filter(model_name=cfg.model_name)
        total_reqs = logs.count()
        tokens = logs.aggregate(
            inp=Sum('input_tokens'),
            out=Sum('output_tokens'),
            tot=Sum('total_tokens'),
            lat=Avg('response_time_ms')
        )
        failures = logs.filter(request_status__in=['failed', 'rate_limited']).count()
        err_rate = round((failures / total_reqs * 100), 1) if total_reqs > 0 else 0.0

        models_data.append({
            'config': cfg,
            'total_requests': total_reqs,
            'input_tokens': tokens['inp'] or 0,
            'output_tokens': tokens['out'] or 0,
            'total_tokens': tokens['tot'] or 0,
            'avg_latency': round(tokens['lat'] or 0.0, 1),
            'failures': failures,
            'error_rate': err_rate,
        })

    context = {
        'page_title': 'Model Comparison',
        'models_data': models_data,
        'active_tab': 'models',
    }
    return render(request, 'chatbot/monitor/models.html', context)


@login_required
def monitor_ratelimits(request):
    """Rate-limit monitoring with historical snapshots and current warning thresholds."""
    snapshots = RateLimitSnapshot.objects.all().order_by('-captured_at')[:30]
    quotas = ModelQuotaConfig.objects.filter(is_active=True)

    today = date.today()
    today_summaries = DailyUsageSummary.objects.filter(date=today)

    status_cards = []
    for q in quotas:
        sum_today = today_summaries.filter(model_name=q.model_name).first()
        used_tokens = sum_today.total_tokens if sum_today else 0
        limit_tokens = q.tokens_per_day

        if limit_tokens and limit_tokens > 0:
            pct = round((used_tokens / limit_tokens) * 100, 1)
            rem = max(0, limit_tokens - used_tokens)
        else:
            pct = None
            rem = None

        status_cards.append({
            'model_name': q.model_name,
            'used_tokens': used_tokens,
            'limit_tokens': limit_tokens,
            'remaining_tokens': rem,
            'pct': pct,
            'rpm': q.requests_per_minute,
            'tpm': q.tokens_per_minute,
            'quota_type': q.get_quota_type_display(),
        })

    context = {
        'page_title': 'Rate-Limit Monitor',
        'snapshots': snapshots,
        'status_cards': status_cards,
        'active_tab': 'ratelimits',
    }
    return render(request, 'chatbot/monitor/ratelimits.html', context)


@login_required
def monitor_speech_to_text(request):
    """Speech-to-Text tracking page for Groq Whisper transcription."""
    stt_logs = APIRequestLog.objects.filter(endpoint__icontains='transcription').order_by('-request_timestamp')
    total_audio_sec = stt_logs.aggregate(s=Sum('audio_duration_seconds'))['s'] or 0.0

    context = {
        'page_title': 'Speech-to-Text Usage',
        'stt_logs': stt_logs[:30],
        'total_requests': stt_logs.count(),
        'total_audio_seconds': round(total_audio_sec, 1),
        'total_audio_minutes': round(total_audio_sec / 60.0, 2),
        'active_tab': 'speech',
    }
    return render(request, 'chatbot/monitor/speech_to_text.html', context)


@login_required
def monitor_quotas(request):
    """Configure model-specific daily and minute quota limits."""
    seed_default_quotas()

    if request.method == 'POST':
        model_id = request.POST.get('model_id')
        cfg = get_object_or_404(ModelQuotaConfig, id=model_id)

        rpm = request.POST.get('rpm')
        rpd = request.POST.get('rpd')
        tpm = request.POST.get('tpm')
        tpd = request.POST.get('tpd')
        quota_type = request.POST.get('quota_type', 'free_tier')

        cfg.requests_per_minute = int(rpm) if rpm and rpm.isdigit() else None
        cfg.requests_per_day = int(rpd) if rpd and rpd.isdigit() else None
        cfg.tokens_per_minute = int(tpm) if tpm and tpm.isdigit() else None
        cfg.tokens_per_day = int(tpd) if tpd and tpd.isdigit() else None
        cfg.quota_type = quota_type
        cfg.save()

        messages.success(request, f"Quota for {cfg.model_name} updated successfully.")
        return redirect('monitor_quotas')

    quotas = ModelQuotaConfig.objects.all().order_by('model_name')
    context = {
        'page_title': 'Quota Configuration',
        'quotas': quotas,
        'active_tab': 'quotas',
    }
    return render(request, 'chatbot/monitor/quotas.html', context)


@login_required
def monitor_settings(request):
    """Application settings, environment variable status, and Groq model configs."""
    api_key = getattr(settings, 'GROQ_API_KEY', '')
    masked_key = (api_key[:7] + '...' + api_key[-4:]) if len(api_key) > 12 else 'Not configured'

    context = {
        'page_title': 'Application Settings',
        'masked_api_key': masked_key,
        'is_key_configured': bool(api_key),
        'configured_model': getattr(settings, 'GROQ_MODEL', 'qwen/qwen3.8-27b'),
        'sound_url': '/static/chatbot_sound.mp3',
        'active_tab': 'settings',
    }
    return render(request, 'chatbot/monitor/settings.html', context)
