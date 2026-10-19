import os
import re
import time
from datetime import date, timedelta
from django.conf import settings
from django.db import transaction
from django.db.models import Sum, Count, Avg, F
from django.utils import timezone
from groq import Groq
from .models import (
    APIRequestLog,
    ModelQuotaConfig,
    DailyUsageSummary,
    RateLimitSnapshot,
)


def get_groq_client():
    api_key = getattr(settings, 'GROQ_API_KEY', os.environ.get('GROQ_API_KEY', ''))
    if not api_key:
        raise ValueError("GROQ_API_KEY is not configured in settings or environment variables.")
    return Groq(api_key=api_key)


def seed_default_quotas():
    """Seeds baseline Groq free-tier quotas if table is empty."""
    default_models = [
        {
            'model_name': 'qwen/qwen3.8-27b',
            'rpm': 30, 'rpd': 14400, 'tpm': 6000, 'tpd': 500000,
            'type': 'free_tier'
        },
        {
            'model_name': 'openai/gpt-oss-120b',
            'rpm': 30, 'rpd': 14400, 'tpm': 8000, 'tpd': 500000,
            'type': 'free_tier'
        },
        {
            'model_name': 'openai/gpt-oss-20b',
            'rpm': 30, 'rpd': 14400, 'tpm': 8000, 'tpd': 500000,
            'type': 'free_tier'
        },
        {
            'model_name': 'allam-2-7b',
            'rpm': 30, 'rpd': 14400, 'tpm': 6000, 'tpd': 500000,
            'type': 'free_tier'
        },
        {
            'model_name': 'whisper-large-v3-turbo',
            'rpm': 20, 'rpd': 2000, 'tpm': 25000, 'tpd': 500000,
            'type': 'free_tier'
        },
    ]

    for item in default_models:
        ModelQuotaConfig.objects.get_or_create(
            model_name=item['model_name'],
            defaults={
                'requests_per_minute': item['rpm'],
                'requests_per_day': item['rpd'],
                'tokens_per_minute': item['tpm'],
                'tokens_per_day': item['tpd'],
                'quota_type': item['type'],
                'is_active': True,
            }
        )


def log_and_aggregate_request(
    model_name,
    endpoint='/openai/v1/chat/completions',
    input_tokens=0,
    output_tokens=0,
    total_tokens=0,
    request_status='success',
    error_message='',
    response_time_ms=0.0,
    user=None,
    usage_source='api_reported',
    estimated_or_actual='actual',
    audio_duration_seconds=0.0,
    rate_limit_headers=None
):
    """
    Persists APIRequestLog and atomically updates DailyUsageSummary to prevent duplicate-counting.
    Also captures RateLimitSnapshot if headers are supplied.
    """
    req_time = timezone.now()
    log_entry = APIRequestLog.objects.create(
        model_name=model_name,
        endpoint=endpoint,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        request_status=request_status,
        error_message=error_message,
        response_time_ms=response_time_ms,
        request_timestamp=req_time,
        user=user,
        usage_source=usage_source,
        estimated_or_actual=estimated_or_actual,
        audio_duration_seconds=audio_duration_seconds,
    )

    # Atomic Daily Summary Aggregation
    today_date = req_time.date()
    with transaction.atomic():
        summary, _ = DailyUsageSummary.objects.select_for_update().get_or_create(
            date=today_date,
            model_name=model_name,
            defaults={
                'total_requests': 0,
                'successful_requests': 0,
                'failed_requests': 0,
                'input_tokens': 0,
                'output_tokens': 0,
                'total_tokens': 0,
                'audio_duration_seconds': 0.0,
            }
        )
        summary.total_requests = F('total_requests') + 1
        if request_status == 'success':
            summary.successful_requests = F('successful_requests') + 1
        else:
            summary.failed_requests = F('failed_requests') + 1

        summary.input_tokens = F('input_tokens') + input_tokens
        summary.output_tokens = F('output_tokens') + output_tokens
        summary.total_tokens = F('total_tokens') + total_tokens
        summary.audio_duration_seconds = F('audio_duration_seconds') + audio_duration_seconds
        summary.save()

    # Capture rate limit headers if provided
    if rate_limit_headers:
        try:
            RateLimitSnapshot.objects.create(
                model_name=model_name,
                captured_at=req_time,
                limit_requests=rate_limit_headers.get('limit_requests'),
                remaining_requests=rate_limit_headers.get('remaining_requests'),
                limit_tokens=rate_limit_headers.get('limit_tokens'),
                remaining_tokens=rate_limit_headers.get('remaining_tokens'),
                reset_requests=rate_limit_headers.get('reset_requests', ''),
                reset_tokens=rate_limit_headers.get('reset_tokens', ''),
                source='api_header'
            )
        except Exception:
            pass

    return log_entry


def extract_rate_limit_headers(raw_response):
    """Safely extracts rate-limit headers from Groq httpx response if present."""
    if not raw_response or not hasattr(raw_response, 'headers'):
        return None

    h = raw_response.headers
    try:
        lr = int(h.get('x-ratelimit-limit-requests')) if 'x-ratelimit-limit-requests' in h else None
        rr = int(h.get('x-ratelimit-remaining-requests')) if 'x-ratelimit-remaining-requests' in h else None
        lt = int(h.get('x-ratelimit-limit-tokens')) if 'x-ratelimit-limit-tokens' in h else None
        rt = int(h.get('x-ratelimit-remaining-tokens')) if 'x-ratelimit-remaining-tokens' in h else None
        reset_req = h.get('x-ratelimit-reset-requests', '')
        reset_tok = h.get('x-ratelimit-reset-tokens', '')

        if any([lr, rr, lt, rt, reset_req, reset_tok]):
            return {
                'limit_requests': lr,
                'remaining_requests': rr,
                'limit_tokens': lt,
                'remaining_tokens': rt,
                'reset_requests': reset_req,
                'reset_tokens': reset_tok,
            }
    except Exception:
        pass
    return None


def get_college_live_context(user=None, query_text=""):
    """
    Assembles real-time college database context for Swecha AI.
    """
    context_lines = [
        "Institution: Sri NRI Junior College (AP / Telangana Intermediate Education)",
        f"Today's Date: {date.today().strftime('%B %d, %Y (%A)')}",
    ]

    try:
        from accounts.models import AcademicYear, Group, Section
        from students.models import Student

        active_year = AcademicYear.objects.filter(is_active=True).first()
        if active_year:
            context_lines.append(f"Active Academic Year: {active_year.name}")

        total_students = Student.objects.filter(is_active=True).count()
        context_lines.append(f"Total Active Students Enrolled: {total_students}")

        groups = Group.objects.all()
        if groups.exists():
            group_stats = []
            for g in groups:
                cnt = Student.objects.filter(section__group=g, is_active=True).count()
                group_stats.append(f"{g.name}: {cnt} students")
            context_lines.append("Groups: " + ", ".join(group_stats))

        try:
            from attendance.models import Attendance
            today = date.today()
            att_records = Attendance.objects.filter(date=today)
            if att_records.exists():
                present_cnt = att_records.filter(status='P').count()
                absent_cnt = att_records.filter(status='A').count()
                context_lines.append(f"Today's Attendance: {present_cnt} Present, {absent_cnt} Absent (Total marked: {att_records.count()})")
        except Exception:
            pass

        is_privileged = user and (getattr(user, 'is_admin', lambda: False)() or getattr(user, 'is_superuser', False))
        if is_privileged:
            try:
                from fees.models import StudentFee, FeePayment
                total_expected = StudentFee.objects.aggregate(total=Sum('total_fee'))['total'] or 0
                total_collected = FeePayment.objects.aggregate(total=Sum('amount'))['total'] or 0
                pending = total_expected - total_collected
                context_lines.append(f"Fee Overview: Total Expected ₹{total_expected:,.0f}, Collected ₹{total_collected:,.0f}, Pending ₹{pending:,.0f}")
            except Exception:
                pass

        if query_text:
            student_hits = []
            numbers = re.findall(r'\b\d{3,10}\b', query_text)
            for num in numbers:
                st = Student.objects.filter(admission_number__icontains=num).first()
                if not st:
                    st = Student.objects.filter(hall_ticket_number__icontains=num).first()
                if st and st not in student_hits:
                    student_hits.append(st)

            words = [w.strip() for w in query_text.split() if len(w.strip()) > 3 and w.lower() not in ['student', 'details', 'check', 'about', 'swecha', 'please', 'marks', 'fees']]
            for word in words[:3]:
                matches = Student.objects.filter(name__icontains=word)[:2]
                for st in matches:
                    if st not in student_hits and len(student_hits) < 3:
                        student_hits.append(st)

            if student_hits:
                context_lines.append("--- Matched Student Records from Database ---")
                for s in student_hits:
                    sec_name = str(s.section) if s.section else 'Not assigned'
                    context_lines.append(
                        f"Student: {s.name} (Adm No: {s.admission_number}, Section: {sec_name}, Father: {s.father_name}, Mobile: {s.mobile}, Active: {s.is_active})"
                    )
    except Exception as e:
        context_lines.append(f"(Context retrieval notice: {str(e)})")

    return "\n".join(context_lines)


def get_system_prompt(user=None, query_text=""):
    college_context = get_college_live_context(user, query_text)
    user_name = user.get_full_name() or user.username if user and user.is_authenticated else "College Staff"
    user_role = user.get_role_display() if user and hasattr(user, 'get_role_display') else "Staff"

    return f"""You are **Swecha** (స్వేచ్ఛ), the official, intelligent AI Assistant of **Sri NRI Junior College**.
The name "Swecha" represents freedom, knowledge empowerment, and academic excellence.

Current User: {user_name} (Role: {user_role})

### Real-Time College Information & Database Context:
{college_context}

### Core Identity & Behavior:
1. **Friendly, Respectful & Intelligent**: Greet users warmly as Swecha. Be polite, concise, professional, and helpful.
2. **Multilingual Proficiency**:
   - Reply fluently in English, Telugu (తెలుగు), or Tanglish (Telugu written in Roman script).
   - Match the language or tone chosen by the user.
3. **Capabilities**:
   - Provide student records, attendance, groups (MPC, BiPC, CEC, MEC), sections, marks, fee details, and college schedules.
   - Guide staff on using the college system (attendance, marks, fee receipts, WhatsApp notifications).
   - Draft official circulars, parent WhatsApp notices, and student congratulatory notes.
   - Academic assistance for Intermediate IPE, EAMCET, and JEE.
4. **Formatting**:
   - Use clean Markdown with bolding, lists, and tables when presenting data.
"""


def ask_swecha(user_message, history=None, user=None):
    """
    Sends message to Groq LLM with live context, logs actual tokens, response latency,
    and captures rate-limit headers into the database tracker.
    """
    client = get_groq_client()
    system_prompt = get_system_prompt(user=user, query_text=user_message)

    messages = [{"role": "system", "content": system_prompt}]
    if history:
        for msg in history[-10:]:
            messages.append({"role": msg['role'], "content": msg['content']})
    messages.append({"role": "user", "content": user_message})

    preferred_model = getattr(settings, 'GROQ_MODEL', 'qwen/qwen3.8-27b')
    fallback_models = ['qwen/qwen3.8-27b', 'openai/gpt-oss-120b', 'openai/gpt-oss-20b']
    if preferred_model in fallback_models:
        fallback_models.remove(preferred_model)
    model_sequence = [preferred_model] + fallback_models

    last_error = None
    endpoint = '/openai/v1/chat/completions'

    for model_name in model_sequence:
        start_time = time.time()
        try:
            # We use with_raw_response to access rate-limit headers
            raw_res = client.chat.completions.with_raw_response.create(
                model=model_name,
                messages=messages,
                temperature=0.6,
                max_tokens=1500,
            )
            elapsed_ms = round((time.time() - start_time) * 1000, 2)
            completion = raw_res.parse()

            # Extract actual token counts
            usage = getattr(completion, 'usage', None)
            if usage:
                in_tok = getattr(usage, 'prompt_tokens', 0) or 0
                out_tok = getattr(usage, 'completion_tokens', 0) or 0
                total_tok = getattr(usage, 'total_tokens', 0) or (in_tok + out_tok)
                usage_src = 'api_reported'
                est_or_act = 'actual'
            else:
                in_tok, out_tok, total_tok = 0, 0, 0
                usage_src = 'unavailable'
                est_or_act = 'estimated'

            # Extract headers from raw httpx response
            rate_headers = extract_rate_limit_headers(raw_res.http_response)

            # Persist usage in tracker
            log_and_aggregate_request(
                model_name=model_name,
                endpoint=endpoint,
                input_tokens=in_tok,
                output_tokens=out_tok,
                total_tokens=total_tok,
                request_status='success',
                response_time_ms=elapsed_ms,
                user=user,
                usage_source=usage_src,
                estimated_or_actual=est_or_act,
                rate_limit_headers=rate_headers
            )

            response_text = completion.choices[0].message.content
            return {
                "success": True,
                "response": response_text,
                "model": model_name,
                "tokens": {
                    "input": in_tok,
                    "output": out_tok,
                    "total": total_tok,
                },
                "latency_ms": elapsed_ms,
            }
        except Exception as e:
            elapsed_ms = round((time.time() - start_time) * 1000, 2)
            err_str = str(e)
            is_429 = '429' in err_str or 'rate' in err_str.lower()
            status = 'rate_limited' if is_429 else 'failed'

            # Log failure in tracker without inventing tokens
            log_and_aggregate_request(
                model_name=model_name,
                endpoint=endpoint,
                input_tokens=0,
                output_tokens=0,
                total_tokens=0,
                request_status=status,
                error_message=err_str[:500],
                response_time_ms=elapsed_ms,
                user=user,
                usage_source='unavailable',
                estimated_or_actual='actual'
            )
            last_error = e
            continue

    return {
        "success": False,
        "response": f"Sorry, I encountered an issue connecting to my AI brain: {str(last_error)}",
        "model": "error",
    }


def get_token_analytics_data(date_filter='today', model_filter=None, start_date=None, end_date=None):
    """
    Computes comprehensive token usage metrics, daily chart series, model breakdowns,
    and quota progress based on the requested date scope.
    """
    now = timezone.now()
    today = now.date()

    # Determine date boundaries
    if date_filter == 'today':
        dt_start = today
        dt_end = today
    elif date_filter == 'yesterday':
        dt_start = today - timedelta(days=1)
        dt_end = dt_start
    elif date_filter == '7d':
        dt_start = today - timedelta(days=6)
        dt_end = today
    elif date_filter == '30d':
        dt_start = today - timedelta(days=29)
        dt_end = today
    elif date_filter == 'month':
        dt_start = today.replace(day=1)
        dt_end = today
    elif date_filter == 'custom' and start_date and end_date:
        dt_start = start_date
        dt_end = end_date
    else:
        dt_start = today - timedelta(days=6)
        dt_end = today

    # Base Queryset
    qs = APIRequestLog.objects.filter(request_timestamp__date__gte=dt_start, request_timestamp__date__lte=dt_end)
    if model_filter and model_filter != 'all':
        qs = qs.filter(model_name=model_filter)

    # Summary aggregations
    agg = qs.aggregate(
        total_input=Sum('input_tokens'),
        total_output=Sum('output_tokens'),
        total_tokens=Sum('total_tokens'),
        total_reqs=Count('id'),
        avg_latency=Avg('response_time_ms'),
        total_audio_sec=Sum('audio_duration_seconds')
    )

    total_input = agg['total_input'] or 0
    total_output = agg['total_output'] or 0
    total_tokens = agg['total_tokens'] or 0
    total_reqs = agg['total_reqs'] or 0
    avg_latency = round(agg['avg_latency'] or 0.0, 1)
    total_audio_sec = round(agg['total_audio_sec'] or 0.0, 1)

    successful_reqs = qs.filter(request_status='success').count()
    failed_reqs = qs.filter(request_status__in=['failed', 'rate_limited']).count()

    # Quota Estimation for Today
    today_qs = APIRequestLog.objects.filter(request_timestamp__date=today)
    if model_filter and model_filter != 'all':
        today_qs = today_qs.filter(model_name=model_filter)
        quota_config = ModelQuotaConfig.objects.filter(model_name=model_filter, is_active=True).first()
    else:
        # If all models selected, find quota config of the primary configured model
        preferred_model = getattr(settings, 'GROQ_MODEL', 'qwen/qwen3.8-27b')
        quota_config = ModelQuotaConfig.objects.filter(model_name=preferred_model, is_active=True).first()

    today_tokens_consumed = today_qs.aggregate(t=Sum('total_tokens'))['t'] or 0

    daily_quota_limit = quota_config.tokens_per_day if quota_config and quota_config.tokens_per_day else None
    if daily_quota_limit and daily_quota_limit > 0:
        remaining_daily_tokens = max(0, daily_quota_limit - today_tokens_consumed)
        daily_usage_pct = round((today_tokens_consumed / daily_quota_limit) * 100, 2)
        quota_label = "Configured Model Quota"
    else:
        remaining_daily_tokens = None
        daily_usage_pct = None
        quota_label = "Quota limit unavailable — check GroqCloud"

    # Chart A & C: Daily Token Consumption & Request Activity Series
    num_days = (dt_end - dt_start).days + 1
    # Cap day points to 31 for charts
    if num_days > 31:
        num_days = 31
        dt_start = dt_end - timedelta(days=30)

    date_labels = []
    input_series = []
    output_series = []
    requests_series = []

    for i in range(num_days):
        cur_date = dt_start + timedelta(days=i)
        date_labels.append(cur_date.strftime('%b %d'))
        day_logs = qs.filter(request_timestamp__date=cur_date)
        day_agg = day_logs.aggregate(
            inp=Sum('input_tokens'),
            out=Sum('output_tokens'),
            cnt=Count('id')
        )
        input_series.append(day_agg['inp'] or 0)
        output_series.append(day_agg['out'] or 0)
        requests_series.append(day_agg['cnt'] or 0)

    # Chart B: Model Comparison Breakdown
    model_rows = (
        qs.values('model_name')
        .annotate(
            tokens=Sum('total_tokens'),
            reqs=Count('id'),
            inputs=Sum('input_tokens'),
            outputs=Sum('output_tokens'),
            avg_lat=Avg('response_time_ms')
        )
        .order_by('-tokens')
    )

    model_labels = [m['model_name'].split('/')[-1] for m in model_rows]
    model_tokens = [m['tokens'] or 0 for m in model_rows]

    # Rate-Limit Warning Level
    warning_level = None
    if daily_usage_pct is not None:
        if daily_usage_pct >= 100:
            warning_level = {'level': 'danger', 'pct': daily_usage_pct, 'msg': '100% Quota Exceeded! Rate limits may apply.'}
        elif daily_usage_pct >= 90:
            warning_level = {'level': 'danger', 'pct': daily_usage_pct, 'msg': '90% Quota Reached. Approaching daily limit.'}
        elif daily_usage_pct >= 80:
            warning_level = {'level': 'warning', 'pct': daily_usage_pct, 'msg': '80% Quota Used. High usage observed.'}
        elif daily_usage_pct >= 50:
            warning_level = {'level': 'info', 'pct': daily_usage_pct, 'msg': '50% Quota Consumed.'}

    return {
        'date_filter': date_filter,
        'model_filter': model_filter or 'all',
        'start_date': dt_start,
        'end_date': dt_end,
        'total_input_tokens': total_input,
        'total_output_tokens': total_output,
        'total_tokens': total_tokens,
        'total_requests': total_reqs,
        'successful_requests': successful_reqs,
        'failed_requests': failed_reqs,
        'avg_latency_ms': avg_latency,
        'total_audio_seconds': total_audio_sec,
        'total_audio_minutes': round(total_audio_sec / 60.0, 2),
        'remaining_daily_tokens': remaining_daily_tokens,
        'daily_usage_pct': daily_usage_pct,
        'daily_quota_limit': daily_quota_limit,
        'quota_label': quota_label,
        'warning_level': warning_level,
        'chart_date_labels': date_labels,
        'chart_input_series': input_series,
        'chart_output_series': output_series,
        'chart_requests_series': requests_series,
        'chart_model_labels': model_labels,
        'chart_model_tokens': model_tokens,
        'model_breakdowns': list(model_rows),
    }
