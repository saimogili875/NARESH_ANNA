from django.contrib import admin
from django.utils import timezone
from .models import User, AcademicYear, Group, Section, LoginSession, ActivityLog

admin.site.register(AcademicYear)


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'academic_year', 'color', 'icon')
    fieldsets = (
        (None, {
            'fields': ('name', 'code', 'academic_year')
        }),
        ('UI Styling', {
            'fields': ('color', 'bg_color', 'border_color', 'icon', 'subjects_text')
        }),
    )

admin.site.register(Section)


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ('username', 'role', 'is_active', 'is_blocked_by_admin', 'blocked_at')
    list_filter = ('role', 'is_active', 'is_blocked_by_admin')
    search_fields = ('username', 'first_name', 'last_name')
    readonly_fields = ('blocked_at',)
    fieldsets = (
        (None, {'fields': ('username', 'role', 'phone', 'is_active')}),
        ('Admin Block', {
            'fields': ('is_blocked_by_admin', 'blocked_reason', 'blocked_at'),
            'description': 'Manually block this user from logging in. Independent of auto-lockout.',
        }),
    )
    actions = ['block_selected_users', 'unblock_selected_users']

    @admin.action(description='🚫 Block selected users')
    def block_selected_users(self, request, queryset):
        now = timezone.now()
        updated = 0
        for user in queryset.filter(is_blocked_by_admin=False):
            user.is_blocked_by_admin = True
            user.blocked_at = now
            user.save(update_fields=['is_blocked_by_admin', 'blocked_at'])
            # Audit log
            ActivityLog.objects.create(
                user=request.user,
                action=f'Blocked user: {user.username}',
                path='/admin/accounts/user/',
                method='ACTION',
            )
            updated += 1
        self.message_user(request, f'{updated} user(s) blocked.')

    @admin.action(description='✅ Unblock selected users')
    def unblock_selected_users(self, request, queryset):
        updated = 0
        for user in queryset.filter(is_blocked_by_admin=True):
            user.is_blocked_by_admin = False
            user.blocked_reason = ''
            user.blocked_at = None
            user.save(update_fields=['is_blocked_by_admin', 'blocked_reason', 'blocked_at'])
            # Audit log
            ActivityLog.objects.create(
                user=request.user,
                action=f'Unblocked user: {user.username}',
                path='/admin/accounts/user/',
                method='ACTION',
            )
            updated += 1
        self.message_user(request, f'{updated} user(s) unblocked.')

    def save_model(self, request, obj, form, change):
        """Log block/unblock when admin edits via the change form."""
        if change and 'is_blocked_by_admin' in form.changed_data:
            if obj.is_blocked_by_admin:
                obj.blocked_at = timezone.now()
                action = f'Blocked user: {obj.username}'
                if obj.blocked_reason:
                    action += f' (reason: {obj.blocked_reason})'
            else:
                obj.blocked_reason = ''
                obj.blocked_at = None
                action = f'Unblocked user: {obj.username}'
            ActivityLog.objects.create(
                user=request.user,
                action=action,
                path=request.path,
                method='ADMIN',
            )
        super().save_model(request, obj, form, change)


# ---------------------------------------------------------------------------
# Login Session + Activity Log
# ---------------------------------------------------------------------------

class ActivityLogInline(admin.TabularInline):
    model = ActivityLog
    extra = 0
    readonly_fields = ('user', 'action', 'path', 'method', 'timestamp')
    fields = ('timestamp', 'action', 'path', 'method')
    ordering = ('timestamp',)
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(LoginSession)
class LoginSessionAdmin(admin.ModelAdmin):
    list_display = (
        'user', 'login_role', 'device_info', 'ip_address',
        'login_time', 'logout_time', 'get_duration', 'is_active',
    )
    list_filter = ('is_active', 'login_time', 'user')
    search_fields = ('user__username', 'ip_address', 'device_info')
    readonly_fields = (
        'user', 'login_role', 'ip_address', 'device_info', 'user_agent_raw',
        'login_time', 'logout_time', 'get_duration', 'is_active',
    )
    inlines = [ActivityLogInline]
    list_per_page = 50

    @admin.display(description='Duration')
    def get_duration(self, obj):
        return obj.duration_display


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ('user', 'action', 'path', 'method', 'timestamp', 'session')
    list_filter = ('method', 'timestamp', 'user')
    search_fields = ('user__username', 'action', 'path')
    readonly_fields = ('session', 'user', 'action', 'path', 'method', 'timestamp')
    list_per_page = 100

    def has_add_permission(self, request):
        return False
