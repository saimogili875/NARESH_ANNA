from django.contrib import admin
from .models import Subject, ExamType, ExamCategory, GroupCategoryConfig, Exam, ExamSubjectMaxMark, Mark, MarksEntryLock, MarksWhatsAppSendLog

@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)

@admin.register(ExamType)
class ExamTypeAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)

class GroupCategoryConfigInline(admin.TabularInline):
    model = GroupCategoryConfig
    extra = 1

@admin.register(ExamCategory)
class ExamCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_fixed_marks', 'bg_color', 'text_color', 'icon')
    search_fields = ('name',)
    list_filter = ('is_fixed_marks',)
    filter_horizontal = ('subjects',)
    inlines = [GroupCategoryConfigInline]

@admin.register(GroupCategoryConfig)
class GroupCategoryConfigAdmin(admin.ModelAdmin):
    list_display = ('group', 'category')
    search_fields = ('group__name', 'category__name')
    list_filter = ('group', 'category')

@admin.register(MarksEntryLock)
class MarksEntryLockAdmin(admin.ModelAdmin):
    list_display = ('exam', 'section', 'subject', 'is_locked', 'locked_by', 'locked_at')
    list_filter = ('is_locked', 'exam', 'section', 'subject')
    search_fields = ('exam__custom_name', 'section__name', 'subject__name', 'locked_by__username')

@admin.register(MarksWhatsAppSendLog)
class MarksWhatsAppSendLogAdmin(admin.ModelAdmin):
    list_display = ('exam', 'section', 'sent_by', 'sent_at', 'student_count')
    list_filter = ('sent_at', 'exam', 'section')
    search_fields = ('exam__custom_name', 'section__name', 'sent_by__username')


