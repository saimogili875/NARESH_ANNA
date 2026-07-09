import json
from django.http import JsonResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

from .services import send_whatsapp_message, send_whatsapp_template


@method_decorator(csrf_exempt, name="dispatch")
class SendMessageView(View):
    """
    POST /whatsapp/send/
    Body: { "to": "+919876543210", "message": "Hello from Django!" }
    """

    def post(self, request):
        try:
            data = json.loads(request.body)
            to = data.get("to")
            message = data.get("message")

            if not to or not message:
                return JsonResponse(
                    {"error": "'to' and 'message' are required fields"},
                    status=400,
                )

            result = send_whatsapp_message(to_number=to, message=message)

            status_code = 200 if result["success"] else 500
            return JsonResponse(result, status=status_code)

        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON body"}, status=400)


@method_decorator(csrf_exempt, name="dispatch")
class SendTemplateView(View):
    """
    POST /whatsapp/send-template/
    Body: { "to": "+919876543210", "template_sid": "HXxxx", "variables": {"1": "John"} }
    """

    def post(self, request):
        try:
            data = json.loads(request.body)
            to = data.get("to")
            template_sid = data.get("template_sid")
            variables = data.get("variables", {})

            if not to or not template_sid:
                return JsonResponse(
                    {"error": "'to' and 'template_sid' are required fields"},
                    status=400,
                )

            result = send_whatsapp_template(
                to_number=to,
                template_sid=template_sid,
                variables=variables,
            )

            status_code = 200 if result["success"] else 500
            return JsonResponse(result, status=status_code)

        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON body"}, status=400)
