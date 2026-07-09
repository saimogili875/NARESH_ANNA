from django.contrib import admin
from .models import User, AcademicYear, Group, Section

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
admin.site.register(User)
