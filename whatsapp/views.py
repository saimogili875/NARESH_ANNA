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
                        logger.info(f"Message {status.get('id')} status: {status.get('status')}")

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
    pending_count = PendingMessage.objects.filter(status=PendingMessage.STATUS_PENDING).count()
    return JsonResponse({
        "success": True,
        "message": "Pending messages queued for the scheduled Cron Job worker.",
        "pending_count": pending_count,
    })
