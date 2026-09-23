import json
import logging
import hmac
import hashlib
from django.shortcuts import render
from django.http import JsonResponse, HttpResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.utils.decorators import method_decorator
from django.conf import settings
from django.contrib.auth.decorators import login_required
from accounts.decorators import admin_required, admin_accounts_required

from .services import send_whatsapp_text, send_whatsapp_template

logger = logging.getLogger('whatsapp_sender')


def _redact_phone(phone):
    if not phone or len(str(phone)) < 6:
        return "*****"
    s = str(phone).strip()
    return f"{s[:3]}******{s[-4:]}"


@csrf_exempt
def meta_webhook(request):
    if request.method == "GET":
        mode = request.GET.get("hub.mode")
        token = request.GET.get("hub.verify_token")
        challenge = request.GET.get("hub.challenge")

        if mode == "subscribe" and token == settings.META_WEBHOOK_VERIFY_TOKEN:
            logger.info("Webhook verified by Meta")
            return HttpResponse(challenge, content_type="text/plain")
        return HttpResponse("Forbidden", status=403)

    if request.method == "POST":
        app_secret = getattr(settings, 'META_APP_SECRET', '')
        if not app_secret:
            logger.error("META_APP_SECRET is not configured in settings — rejecting webhook request")
            return HttpResponse("Forbidden", status=403)

        signature_header = request.headers.get("X-Hub-Signature-256") or request.META.get("HTTP_X_HUB_SIGNATURE_256", "")
        if not signature_header or not signature_header.startswith("sha256="):
            logger.warning("Missing or invalid X-Hub-Signature-256 header")
            return HttpResponse("Forbidden", status=403)

        expected_hash = hmac.new(app_secret.encode('utf-8'), request.body, hashlib.sha256).hexdigest()
        expected_header = f"sha256={expected_hash}"
        if not hmac.compare_digest(signature_header, expected_header):
            logger.warning("X-Hub-Signature-256 signature verification failed")
            return HttpResponse("Forbidden", status=403)

        try:
            data = json.loads(request.body)
            entries = data.get("entry", [])
            for entry in entries:
                for change in entry.get("changes", []):
                    value = change.get("value", {})
                    statuses = value.get("statuses", [])
                    for status in statuses:
                        status_val = status.get('status')
                        wamid_id = status.get('id')
                        error_detail = ""
                        recipient = _redact_phone(status.get('recipient_id'))
                        if status_val == 'failed':
                            errors = status.get('errors', [])
                            error_detail = "; ".join(
                                f"code={e.get('code')} title={e.get('title')}"
                                for e in errors
                            )
                            logger.error(f"Message {wamid_id} FAILED: {error_detail} | recipient={recipient}")
                        else:
                            logger.info(f"Message {wamid_id} status: {status_val}")

                        if wamid_id:
                            from .models import PendingMessage
                            pending_msg = PendingMessage.objects.filter(wamid=wamid_id).first()
                            if pending_msg:
                                if status_val == 'delivered':
                                    pending_msg.status = PendingMessage.STATUS_DELIVERED
                                    pending_msg.save()
                                elif status_val == 'read':
                                    pending_msg.status = PendingMessage.STATUS_READ
                                    pending_msg.save()
                                elif status_val == 'failed':
                                    pending_msg.status = PendingMessage.STATUS_FAILED
                                    if error_detail:
                                        pending_msg.error_message = error_detail
                                    pending_msg.save()

                    incoming = value.get("messages", [])
                    for msg in incoming:
                        from_number = _redact_phone(msg.get("from"))
                        logger.info(f"Incoming message event from {from_number}")
        except Exception as e:
            logger.exception(f"Webhook processing error: {e}")
            return HttpResponse("Internal Server Error", status=500)

        return HttpResponse("OK", status=200)

    return HttpResponse("Method not allowed", status=405)


@method_decorator(login_required, name="dispatch")
@method_decorator(admin_required, name="dispatch")
class SendMessageView(View):
    def post(self, request):
        try:
            data = json.loads(request.body)
            to = data.get("to")
            message = data.get("message")

            if not to or not message:
                return JsonResponse({"error": "'to' and 'message' are required"}, status=400)

            result = send_whatsapp_text(to_number=to, message=message)
            status_code = 200 if result["success"] else result.get("status_code", 502)
            return JsonResponse(result, status=status_code)

        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON body"}, status=400)


@method_decorator(login_required, name="dispatch")
@method_decorator(admin_required, name="dispatch")
class SendTemplateView(View):
    def post(self, request):
        try:
            data = json.loads(request.body)
            to = data.get("to")
            template_name = data.get("template_name")
            components = data.get("components", [])

            if not to or not template_name:
                return JsonResponse({"error": "'to' and 'template_name' are required"}, status=400)

            result = send_whatsapp_template(
                to_number=to,
                template_name=template_name,
                components=components,
            )
            status_code = 200 if result["success"] else result.get("status_code", 502)
            return JsonResponse(result, status=status_code)

        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON body"}, status=400)


@require_POST
@login_required
@admin_required
def trigger_batch_webhook(request):
    from whatsapp.models import PendingMessage
    from .services import send_whatsapp_text, send_whatsapp_template, build_template_components

    pending = list(
        PendingMessage.objects.filter(
            status=PendingMessage.STATUS_PENDING
        ).order_by('created_at')[:50]
    )

    if not pending:
        return JsonResponse({"success": True, "message": "No pending messages.", "sent": 0, "failed": 0})

    sent = 0
    failed = 0
    for msg in pending:
        phone = (msg.phone or "").strip()
        if not phone:
            msg.status = PendingMessage.STATUS_FAILED
            msg.error_message = "No phone number"
            msg.save()
            failed += 1
            continue

        if getattr(msg, 'message_type', 'template') == PendingMessage.TYPE_TEMPLATE:
            template_name = msg.template_name or getattr(settings, 'META_TEMPLATE_GENERAL', 'general_notification')
            params = msg.template_params or [msg.message]
            components = build_template_components(params)
            language = msg.language or getattr(settings, 'WHATSAPP_DEFAULT_LANGUAGE', 'en')
            result = send_whatsapp_template(
                to_number=phone,
                template_name=template_name,
                language=language,
                components=components
            )
            if not result["success"]:
                logger.error(f"PendingMessage {msg.pk} template '{template_name}' failed: {result.get('error')}")
        else:
            result = send_whatsapp_text(to_number=phone, message=msg.message)

        if result["success"]:
            msg.status = PendingMessage.STATUS_SENT
            msg.wamid = result.get('wamid') or result.get('message_id') or ''
            msg.error_message = ""
            msg.save()
            sent += 1
        else:
            msg.status = PendingMessage.STATUS_FAILED
            msg.error_message = result.get("error", "Unknown error")
            msg.save()
            failed += 1

    return JsonResponse({
        "success": True,
        "message": f"Dispatched: {sent} sent, {failed} failed out of {len(pending)}.",
        "sent": sent,
        "failed": failed,
    })


@require_POST
@login_required
@admin_required
def retry_failed_messages(request):
    from whatsapp.models import PendingMessage
    from .services import dispatch_pending_messages_async

    failed_msgs = list(PendingMessage.objects.filter(status=PendingMessage.STATUS_FAILED))
    reset_count = len(failed_msgs)

    if reset_count == 0:
        return JsonResponse({"success": True, "message": "No failed messages to retry.", "reset": 0})

    for msg in failed_msgs:
        if msg.template_name == 'marks_template' and msg.template_params and len(msg.template_params) > 5:
            msg.template_params = msg.template_params[:5]
        msg.status = PendingMessage.STATUS_PENDING
        msg.error_message = ''
        msg.save()

    dispatch_pending_messages_async(batch_size=50)
    return JsonResponse({
        "success": True,
        "message": f"Reset {reset_count} failed messages. Dispatching in background.",
        "reset": reset_count,
    })


@login_required
@admin_required
def message_status_list(request):
    from .models import PendingMessage
    from django.db.models import Q

    q = request.GET.get('q', '').strip()
    messages_qs = PendingMessage.objects.select_related('student').order_by('-created_at')

    if q:
        messages_qs = messages_qs.filter(
            Q(student__name__icontains=q) |
            Q(phone__icontains=q)
        )
    else:
        messages_qs = messages_qs[:20]

    context = {
        'messages_list': messages_qs,
        'search_query': q,
    }
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'
    if is_ajax:
        return render(request, 'whatsapp/_status_table.html', context)

    return render(request, 'whatsapp/message_status.html', context)

