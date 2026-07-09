from django.contrib import admin
from .models import Subject, ExamType, ExamCategory, GroupCategoryConfig, Exam, ExamSubjectMaxMark, Mark

@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)

@admin.register(ExamType)
class ExamTypeAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)

@admin.register(ExamCategory)
class ExamCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_fixed_marks', 'bg_color', 'text_color', 'icon')
    search_fields = ('name',)
    list_filter = ('is_fixed_marks',)
    filter_horizontal = ('subjects',)

@admin.register(GroupCategoryConfig)
class GroupCategoryConfigAdmin(admin.ModelAdmin):
    list_display = ('group', 'category')
    list_filter = ('group', 'category')

