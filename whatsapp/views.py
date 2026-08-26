import json
import logging
from django.http import JsonResponse, HttpResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.conf import settings

from .services import send_whatsapp_text, send_whatsapp_template

logger = logging.getLogger('whatsapp_sender')


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
        try:
            data = json.loads(request.body)
            entries = data.get("entry", [])
            for entry in entries:
                for change in entry.get("changes", []):
                    value = change.get("value", {})
                    statuses = value.get("statuses", [])
                    for status in statuses:
                        status_val = status.get('status')
                        if status_val == 'failed':
                            errors = status.get('errors', [])
                            error_detail = "; ".join(
                                f"code={e.get('code')} title={e.get('title')} detail={e.get('error_data', {}).get('details', e.get('message', ''))}"
                                for e in errors
                            )
                            logger.error(f"Message {status.get('id')} FAILED: {error_detail} | recipient={status.get('recipient_id')}")
                        else:
                            logger.info(f"Message {status.get('id')} status: {status_val}")

                    incoming = value.get("messages", [])
                    for msg in incoming:
                        from_number = msg.get("from")
                        msg_type = msg.get("type")
                        if msg_type == "text":
                            text = msg.get("text", {}).get("body", "")
                            logger.info(f"Incoming from {from_number}: {text}")
        except Exception as e:
            logger.error(f"Webhook processing error: {e}")

        return HttpResponse("OK", status=200)

    return HttpResponse("Method not allowed", status=405)


@method_decorator(csrf_exempt, name="dispatch")
class SendMessageView(View):
    def post(self, request):
        try:
            data = json.loads(request.body)
            to = data.get("to")
            message = data.get("message")

            if not to or not message:
                return JsonResponse({"error": "'to' and 'message' are required"}, status=400)

            result = send_whatsapp_text(to_number=to, message=message)
            status_code = 200 if result["success"] else 500
            return JsonResponse(result, status=status_code)

        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON body"}, status=400)


@method_decorator(csrf_exempt, name="dispatch")
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
            status_code = 200 if result["success"] else 500
            return JsonResponse(result, status=status_code)

        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON body"}, status=400)


@csrf_exempt
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


@csrf_exempt
def retry_failed_messages(request):
    from whatsapp.models import PendingMessage
    from .services import dispatch_pending_messages

    reset_count = PendingMessage.objects.filter(
        status=PendingMessage.STATUS_FAILED
    ).update(status=PendingMessage.STATUS_PENDING, error_message='')

    if reset_count == 0:
        return JsonResponse({"success": True, "message": "No failed messages to retry.", "reset": 0})

    result = dispatch_pending_messages(batch_size=reset_count)
    return JsonResponse({
        "success": True,
        "message": f"Reset {reset_count} failed messages. Sent: {result['sent']}, Failed: {result['failed']}.",
        "reset": reset_count,
        "sent": result["sent"],
        "failed": result["failed"],
    })
