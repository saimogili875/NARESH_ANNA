from django.contrib import admin
from .models import PendingMessage, WhatsAppSession


@admin.register(PendingMessage)
class PendingMessageAdmin(admin.ModelAdmin):
    list_display = ['student', 'phone', 'status', 'created_at', 'updated_at', 'short_message', 'error_message']
    list_filter = ['status', 'created_at']
    search_fields = ['student__name', 'phone', 'message', 'error_message']

    def short_message(self, obj):
        return obj.message[:50] + '...' if len(obj.message) > 50 else obj.message
    short_message.short_description = 'Message'


@admin.register(WhatsAppSession)
class WhatsAppSessionAdmin(admin.ModelAdmin):
    list_display = ['__str__', 'updated_at', 'created_at']

