from django.urls import path
from .views import SendMessageView, SendTemplateView, trigger_batch_webhook

urlpatterns = [
    path("send/", SendMessageView.as_view(), name="whatsapp-send"),
    path("send-template/", SendTemplateView.as_view(), name="whatsapp-send-template"),
    path("trigger-batch/", trigger_batch_webhook, name="whatsapp-trigger-batch"),
]

