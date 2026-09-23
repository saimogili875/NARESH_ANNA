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
        self.fields['address'].widget = forms.Textarea(attrs={'class': 'form-control', 'rows': 2})
        self.fields['section'].widget.attrs['class'] = 'form-select'
        self.fields['academic_year'].widget.attrs['class'] = 'form-select'
        self.fields['photo'].widget.attrs['class'] = 'form-control'
        self.fields['photo'].help_text = 'Maximum photo upload size is 10 MB.'
        self.fields['mother_name'].required = False
        for f in ('marks_telugu', 'marks_hindi', 'marks_english', 'marks_maths',
                  'marks_physics', 'marks_biology', 'marks_social', 'marks_total'):
            self.fields[f].widget = forms.NumberInput(attrs={
                'class': 'form-control', 'min': '0', 'max': '100', 'step': '0.01'
            })
            self.fields[f].required = False

    def clean_hall_ticket_number(self):
        value = self.cleaned_data.get('hall_ticket_number', '')
        if value and not value.isdigit():
            raise ValidationError('Hall ticket number must contain digits only.')
        return value

    def _clean_mobile_field(self, field_name):
        value = self.cleaned_data.get(field_name, '')
        if value:
            if not value.isdigit():
                raise ValidationError('Mobile number must contain digits only.')
            if len(value) != 10:
                raise ValidationError('Mobile number must be exactly 10 digits.')
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
            if not value.isdigit():
                raise ValidationError('Aadhaar number must contain digits only.')
            if len(value) != 12:
                raise ValidationError('Aadhaar number must be exactly 12 digits.')
        return value


    def clean_photo(self):
        photo = self.cleaned_data.get('photo')
        if isinstance(photo, UploadedFile):
            size_mb = photo.size / (1024 * 1024)
            if size_mb > 10:
                raise ValidationError(f'Photo is too large ({size_mb:.1f} MB). Maximum size is 10 MB.')
        return photo


class StudentSearchForm(forms.Form):
    q = forms.CharField(required=False, widget=forms.TextInput(attrs={
        'class': 'form-control',
        'placeholder': 'Search by name, admission no, mobile, aadhaar...'
    }))
