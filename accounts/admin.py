from django.contrib import admin
from django.utils import timezone
from django.contrib.admin.sites import NotRegistered
from axes.models import AccessAttempt
from .models import User, AcademicYear, Group, Section, LoginSession, ActivityLog

from django.contrib import messages
from students.models import Student

@admin.register(AcademicYear)
class AcademicYearAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active', 'start_date', 'end_date')
    list_editable = ('is_active',)
    list_filter = ('is_active',)

    def delete_model(self, request, obj):
        student_count = Student.objects.filter(academic_year=obj).count()
        if student_count > 0:
            self.message_user(
                request,
                f'Cannot delete Academic Year "{obj.name}": {student_count} student(s) are assigned to it.',
                level=messages.ERROR
            )
            return
        super().delete_model(request, obj)


class SectionInline(admin.TabularInline):
    model = Section
    extra = 0
    show_change_link = True


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'academic_year', 'color', 'icon')
    inlines = [SectionInline]
    fieldsets = (
        (None, {
            'fields': ('name', 'code', 'academic_year')
        }),
        ('UI Styling', {
            'fields': ('color', 'bg_color', 'border_color', 'icon', 'subjects_text')
        }),
    )

    def get_deleted_objects(self, objs, request):
        deleted_objects, model_count, perms_needed, protected = super().get_deleted_objects(objs, request)
        new_protected = []
        for obj in objs:
            student_count = Student.objects.filter(section__group=obj).count()
            if student_count > 0:
                new_protected.append(f'Group "{obj.name}" has {student_count} student(s) assigned. Reassign or remove students first.')
            elif obj.sections.exists():
                new_protected.append(f'Group "{obj.name}" has {obj.sections.count()} section(s). Delete this group\'s sections first, or use the Groups page in the app.')
        if new_protected:
            protected = new_protected
        return deleted_objects, model_count, perms_needed, protected

    def delete_model(self, request, obj):
        student_count = Student.objects.filter(section__group=obj).count()
        if student_count > 0:
            self.message_user(
                request,
                f'Cannot delete Group "{obj.name}": {student_count} student(s) are assigned to it.',
                level=messages.ERROR
            )
            return
        if obj.sections.exists():
            self.message_user(
                request,
                f'Cannot delete Group "{obj.name}": Delete this group\'s sections first, or use the Groups page in the app.',
                level=messages.WARNING
            )
            return
        super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        from django.db import IntegrityError
        from django.db.models import ProtectedError
        deleted_count = 0
        for obj in list(queryset):
            student_count = Student.objects.filter(section__group=obj).count()
            if student_count > 0:
                self.message_user(
                    request,
                    f'Cannot delete Group "{obj.name}": {student_count} student(s) are assigned to it.',
                    level=messages.ERROR
                )
            elif obj.sections.exists():
                self.message_user(
                    request,
                    f'Cannot delete Group "{obj.name}": Delete this group\'s sections first, or use the Groups page in the app.',
                    level=messages.WARNING
                )
            else:
                try:
                    obj.delete()
                    deleted_count += 1
                except (ProtectedError, IntegrityError):
                    self.message_user(
                        request,
                        f'Cannot delete Group "{obj.name}": Protected related objects exist.',
                        level=messages.ERROR
                    )
        if deleted_count > 0:
            self.message_user(request, f'Successfully deleted {deleted_count} group(s).', level=messages.SUCCESS)


@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'group', 'year', 'name', 'academic_year')
    list_filter = ('year', 'group', 'academic_year')

    def get_deleted_objects(self, objs, request):
        deleted_objects, model_count, perms_needed, protected = super().get_deleted_objects(objs, request)
        new_protected = []
        for obj in objs:
            student_count = Student.objects.filter(section=obj).count()
            if student_count > 0:
                new_protected.append(f'Section "{obj}" has {student_count} student(s) assigned. Reassign or remove students first.')
        if new_protected:
            protected = new_protected
        return deleted_objects, model_count, perms_needed, protected

    def delete_model(self, request, obj):
        student_count = Student.objects.filter(section=obj).count()
        if student_count > 0:
            self.message_user(
                request,
                f'Cannot delete Section "{obj}": {student_count} student(s) are assigned to it.',
                level=messages.ERROR
            )
            return
        super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        from django.db import IntegrityError
        from django.db.models import ProtectedError
        deleted_count = 0
        for obj in list(queryset):
            student_count = Student.objects.filter(section=obj).count()
            if student_count > 0:
                self.message_user(
                    request,
                    f'Cannot delete Section "{obj}": {student_count} student(s) are assigned to it.',
                    level=messages.ERROR
                )
            else:
                try:
                    obj.delete()
                    deleted_count += 1
                except (ProtectedError, IntegrityError):
                    self.message_user(
                        request,
                        f'Cannot delete Section "{obj}": Protected related objects exist.',
                        level=messages.ERROR
                    )
        if deleted_count > 0:
            self.message_user(request, f'Successfully deleted {deleted_count} section(s).', level=messages.SUCCESS)




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

    def get_actions(self, request):
        actions = super().get_actions(request)
        if not request.user.is_superuser:
            if 'unblock_selected_users' in actions:
                del actions['unblock_selected_users']
        return actions

    def get_readonly_fields(self, request, obj=None):
        readonly = tuple(self.readonly_fields)
        if not request.user.is_superuser:
            if obj and obj.is_blocked_by_admin:
                return readonly + ('is_blocked_by_admin',)
        return readonly

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
        if not request.user.is_superuser:
            self.message_user(request, "Only admins (superusers) can unblock users.", level='ERROR')
            return
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


# ---------------------------------------------------------------------------
# Django-Axes Lockout Management
# ---------------------------------------------------------------------------

try:
    admin.site.unregister(AccessAttempt)
except NotRegistered:
    pass

@admin.register(AccessAttempt)
class CustomAccessAttemptAdmin(admin.ModelAdmin):
    list_display = ('username', 'ip_address', 'failures_since_start', 'attempt_time')
    list_filter = ('ip_address', 'username', 'attempt_time')
    search_fields = ('ip_address', 'username')
    actions = ['unlock_attempts']

    @admin.action(description='🔓 Unlock selected attempts (Clears lockout)')
    def unlock_attempts(self, request, queryset):
        # Deleting the AccessAttempt record is how axes removes the lockout
        deleted, _ = queryset.delete()
        self.message_user(request, f'Unlocked {deleted} lockout attempt(s).')
