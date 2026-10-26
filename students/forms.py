from django import forms
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile
from .models import Student

DIGITS_ONLY = {'pattern': r'[0-9]*', 'inputmode': 'numeric'}


class StudentForm(forms.ModelForm):
    class Meta:
        model = Student
        fields = ['admission_number', 'hall_ticket_number', 'name', 'father_name',
                  'mother_name', 'mobile', 'second_mobile', 'third_mobile', 'fourth_mobile',
                  'aadhaar', 'apaar_id', 'sport', 'address', 'section', 'academic_year', 'photo',
                  'prev_school_name', 'prev_school_location',
                  'marks_telugu', 'marks_hindi', 'marks_english', 'marks_maths',
                  'marks_physics', 'marks_biology', 'marks_social', 'marks_total']
        widgets = {
            f: forms.TextInput(attrs={'class': 'form-control'})
            for f in ['admission_number', 'name', 'father_name', 'mother_name',
                      'aadhaar', 'apaar_id', 'sport', 'prev_school_name', 'prev_school_location']
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Hall ticket — numbers only
        self.fields['hall_ticket_number'].widget = forms.TextInput(attrs={
            'class': 'form-control', **DIGITS_ONLY
        })
        # All mobile fields — numbers only
        for field in ('mobile', 'second_mobile', 'third_mobile', 'fourth_mobile'):
            self.fields[field].widget = forms.TextInput(attrs={
                'class': 'form-control', **DIGITS_ONLY
            })
            self.fields[field].max_length = 25
            self.fields[field].validators = [v for v in self.fields[field].validators if not hasattr(v, 'limit_value') or v.limit_value > 25]

        self.fields['aadhaar'].max_length = 30
        self.fields['aadhaar'].validators = [v for v in self.fields['aadhaar'].validators if not hasattr(v, 'limit_value') or v.limit_value > 30]
        self.fields['address'].widget = forms.Textarea(attrs={'class': 'form-control', 'rows': 2})
        self.fields['section'].widget.attrs['class'] = 'form-select'
        self.fields['academic_year'].widget.attrs['class'] = 'form-select'
        self.fields['photo'].widget.attrs['class'] = 'form-control'
        self.fields['photo'].help_text = 'Maximum photo upload size is 10 MB.'
        self.fields['father_name'].required = False
        self.fields['mother_name'].required = False
        self.fields['section'].required = False
        self.fields['academic_year'].required = False

        from accounts.models import AcademicYear
        if not self.instance.pk:
            active_year = AcademicYear.objects.filter(is_active=True).first()
            if active_year:
                self.fields['academic_year'].initial = active_year

        for f in ('marks_telugu', 'marks_hindi', 'marks_english', 'marks_maths',
                  'marks_physics', 'marks_biology', 'marks_social', 'marks_total'):
            self.fields[f].widget = forms.NumberInput(attrs={
                'class': 'form-control', 'min': '0', 'max': '100', 'step': '0.01'
            })
            self.fields[f].required = False

    def clean_hall_ticket_number(self):
        value = self.cleaned_data.get('hall_ticket_number', '')
        if value:
            value = str(value).strip()
            if not value.isdigit():
                raise ValidationError('Hall ticket number must contain digits only.')
        return value

    def _clean_mobile_field(self, field_name):
        value = self.cleaned_data.get(field_name, '')
        if value:
            clean_val = str(value).strip().replace(' ', '').replace('-', '')
            if clean_val.startswith('+91'):
                clean_val = clean_val[3:]
            elif clean_val.startswith('91') and len(clean_val) == 12:
                clean_val = clean_val[2:]
            if not clean_val.isdigit():
                raise ValidationError('Mobile number must contain digits only.')
            if len(clean_val) != 10:
                raise ValidationError(f'Mobile number must be exactly 10 digits (got {len(clean_val)} digits).')
            return clean_val
        return value

    def clean_mobile(self):
        return self._clean_mobile_field('mobile')

    def clean_second_mobile(self):
        return self._clean_mobile_field('second_mobile')

    def clean_third_mobile(self):
        return self._clean_mobile_field('third_mobile')

    def clean_fourth_mobile(self):
        return self._clean_mobile_field('fourth_mobile')

    def clean_aadhaar(self):
        value = self.cleaned_data.get('aadhaar', '')
        if value:
            clean_val = str(value).strip().replace(' ', '').replace('-', '')
            if not clean_val.isdigit():
                raise ValidationError('Aadhaar number must contain digits only.')
            if len(clean_val) != 12:
                raise ValidationError(f'Aadhaar number must be exactly 12 digits (got {len(clean_val)} digits).')
            return clean_val
        return value

    def clean_photo(self):
        photo = self.cleaned_data.get('photo')
        if isinstance(photo, UploadedFile):
            size_mb = photo.size / (1024 * 1024)
            if size_mb > 10:
                raise ValidationError(f'Photo is too large ({size_mb:.1f} MB). Maximum size is 10 MB.')
        return photo

    def save(self, commit=True):
        instance = super().save(commit=False)
        if not instance.academic_year:
            from accounts.models import AcademicYear
            active_year = AcademicYear.objects.filter(is_active=True).first()
            if active_year:
                instance.academic_year = active_year
        if commit:
            instance.save()
            self.save_m2m()
        return instance


class StudentSearchForm(forms.Form):
    q = forms.CharField(required=False, widget=forms.TextInput(attrs={
        'class': 'form-control',
        'placeholder': 'Search by name, admission no, mobile, aadhaar...'
    }))
