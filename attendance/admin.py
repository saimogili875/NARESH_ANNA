from django.contrib import admin
from .models import Attendance, AttendanceWindow


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ['student', 'date', 'status', 'section', 'remarks']
    list_filter = ['date', 'status', 'section']
    search_fields = ['student__name', 'student__admission_number']


@admin.register(AttendanceWindow)
class AttendanceWindowAdmin(admin.ModelAdmin):
    list_display = ['__str__', 'start_time', 'end_time', 'is_active']
    list_editable = ['start_time', 'end_time', 'is_active']
