from django.contrib import admin
from .models import Faculty, FacultyAttendance


@admin.register(Faculty)
class FacultyAdmin(admin.ModelAdmin):
    list_display = ('employee_id', 'name', 'subject', 'phone', 'is_active')
    list_filter = ('is_active', 'subject')
    search_fields = ('name', 'employee_id', 'email')
    filter_horizontal = ('assigned_sections', 'assigned_subjects')


@admin.register(FacultyAttendance)
class FacultyAttendanceAdmin(admin.ModelAdmin):
    list_display = ('faculty', 'date', 'status')
    list_filter = ('status', 'date')
    search_fields = ('faculty__name',)
