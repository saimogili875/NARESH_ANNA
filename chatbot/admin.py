from django.contrib import admin
from .models import ChatConversation, ChatMessage


class ChatMessageInline(admin.TabularInline):
    model = ChatMessage
    extra = 0
    readonly_fields = ['role', 'content', 'created_at']
    can_delete = True


@admin.register(ChatConversation)
class ChatConversationAdmin(admin.ModelAdmin):
    list_display = ['title', 'user', 'session_id', 'created_at', 'updated_at']
    list_filter = ['created_at', 'user']
    search_fields = ['title', 'session_id', 'user__username', 'user__first_name']
    inlines = [ChatMessageInline]


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ['conversation', 'role', 'short_content', 'created_at']
    list_filter = ['role', 'created_at']
    search_fields = ['content']

    def short_content(self, obj):
        return obj.content[:80]
    short_content.short_description = 'Content'
