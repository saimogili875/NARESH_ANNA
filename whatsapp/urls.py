from django.urls import path
from .views import SendMessageView, SendTemplateView

urlpatterns = [
    path("send/", SendMessageView.as_view(), name="whatsapp-send"),
    path("send-template/", SendTemplateView.as_view(), name="whatsapp-send-template"),
]
