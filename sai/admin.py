from django.contrib import admin
from .models import LabPerformanceReport


@admin.register(LabPerformanceReport)
class LabPerformanceReportAdmin(admin.ModelAdmin):
    list_display = ('student', 'academic_year', 'jee_best_score', 'eamcet_best_score', 'ipe_percentage', 'date_of_report')
    list_filter = ('academic_year', 'date_of_report')
    search_fields = ('student__name', 'student__admission_number')
    readonly_fields = ('date_of_report',)
    
    fieldsets = (
        ('Student Information', {
            'fields': ('student', 'academic_year', 'date_of_report')
        }),
        ('JEE Main Mock Tests', {
            'fields': ('jee_best_score', 'jee_avg_score', 'jee_mocks_attended')
        }),
        ('EAMCET Mock Tests', {
            'fields': ('eamcet_best_score', 'eamcet_avg_score', 'eamcet_mocks_attended')
        }),
        ('IPE - Mid Term', {
            'fields': ('ipe_score', 'ipe_percentage')
        }),
        ('Weekly Tests', {
            'fields': ('weekly_avg_score',)
        }),
        ('Additional', {
            'fields': ('remarks',)
        }),
    )
