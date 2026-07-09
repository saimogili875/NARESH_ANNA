from django.db import models
from students.models import Student
from accounts.models import AcademicYear


class LabPerformanceReport(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='lab_reports')
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE)
    date_of_report = models.DateField(auto_now_add=True)
    
    # JEE Main Mock Tests
    jee_best_score = models.IntegerField(null=True, blank=True)
    jee_avg_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    jee_mocks_attended = models.IntegerField(null=True, blank=True)
    
    # EAMCET Mock Tests
    eamcet_best_score = models.IntegerField(null=True, blank=True)
    eamcet_avg_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    eamcet_mocks_attended = models.IntegerField(null=True, blank=True)
    
    # IPE - Mid Term
    ipe_score = models.IntegerField(null=True, blank=True)
    ipe_percentage = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    
    # Weekly Tests
    weekly_avg_score = models.IntegerField(null=True, blank=True)
    
    # Remarks
    remarks = models.TextField(blank=True, help_text="General remarks about performance")
    
    class Meta:
        ordering = ['-date_of_report']
    
    def __str__(self):
        return f"{self.student.name} - Lab Report ({self.date_of_report.year})"
