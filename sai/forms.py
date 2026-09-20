from django import forms
from django.core.exceptions import ValidationError
from students.models import Student
from accounts.models import AcademicYear
from .models import LabPerformanceReport


class LabPerformanceReportForm(forms.ModelForm):
    class Meta:
        model = LabPerformanceReport
        fields = [
            'student', 'academic_year',
            'jee_best_score', 'jee_avg_score', 'jee_mocks_attended',
            'eamcet_best_score', 'eamcet_avg_score', 'eamcet_mocks_attended',
            'ipe_score', 'ipe_percentage', 'weekly_avg_score', 'remarks'
        ]
        widgets = {
            'student': forms.Select(attrs={'class': 'form-select'}),
            'academic_year': forms.Select(attrs={'class': 'form-select'}),
            'jee_best_score': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Out of 300', 'min': 0, 'max': 300}),
            'jee_avg_score': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '0.0', 'step': 0.1}),
            'jee_mocks_attended': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'eamcet_best_score': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Out of 160', 'min': 0, 'max': 160}),
            'eamcet_avg_score': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '0.0', 'step': 0.1}),
            'eamcet_mocks_attended': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'ipe_score': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Out of 440', 'min': 0, 'max': 440}),
            'ipe_percentage': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '0.00', 'step': 0.01, 'min': 0, 'max': 100}),
            'weekly_avg_score': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Out of 100', 'min': 0, 'max': 100}),
            'remarks': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'Enter any remarks or comments'}),
        }
        labels = {
            'student': 'Student Name *',
            'academic_year': 'Academic Year *',
            'jee_best_score': 'JEE Best Score (out of 300)',
            'jee_avg_score': 'JEE Average Score',
            'jee_mocks_attended': 'JEE Mocks Attended',
            'eamcet_best_score': 'EAMCET Best Score (out of 160)',
            'eamcet_avg_score': 'EAMCET Average Score',
            'eamcet_mocks_attended': 'EAMCET Mocks Attended',
            'ipe_score': 'IPE Mid-Term Score (out of 440)',
            'ipe_percentage': 'IPE Percentage',
            'weekly_avg_score': 'Weekly Tests Average (out of 100)',
            'remarks': 'Remarks',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['student'].queryset = Student.objects.filter(is_active=True).order_by('name')
        self.fields['academic_year'].queryset = AcademicYear.objects.all().order_by('-name')
