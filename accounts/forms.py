from django import forms
from django.contrib.auth.hashers import make_password
from .models import User, Group, Section, AcademicYear


class LoginForm(forms.Form):
    ROLE_CHOICES = [
        ('', 'Select Role'),
        ('admin', 'Admin'),
        ('faculty', 'Faculty'),
        ('accounts', 'Accounts'),
    ]
    role = forms.ChoiceField(choices=ROLE_CHOICES, widget=forms.Select(attrs={'class': 'form-select'}))
    username = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Username'}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Password'}))


class UserForm(forms.ModelForm):
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
        required=False,
        help_text='Leave blank to keep existing password.'
    )

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'role', 'phone', 'password', 'is_active']
        widgets = {f: forms.TextInput(attrs={'class': 'form-control'}) for f in ['username', 'first_name', 'last_name', 'email', 'phone']}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['role'].widget.attrs['class'] = 'form-select'
        self.fields['role'].choices = [('faculty', 'Faculty'), ('accounts', 'Accounts')]

    def save(self, commit=True):
        user = super().save(commit=False)
        pw = self.cleaned_data.get('password')
        if pw:
            # New password provided — hash and set it
            user.set_password(pw)
        elif self.instance.pk:
            # FIX: editing existing user with blank password — keep the existing hashed password
            user.password = User.objects.get(pk=self.instance.pk).password
        if commit:
            user.save()
        return user


class GroupForm(forms.ModelForm):
    class Meta:
        model = Group
        fields = ['name', 'code', 'academic_year']
        widgets = {f: forms.TextInput(attrs={'class': 'form-control'}) for f in ['name', 'code']}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['academic_year'].widget.attrs['class'] = 'form-select'


class SectionForm(forms.ModelForm):
    class Meta:
        model = Section
        fields = ['group', 'year', 'name', 'academic_year']
        widgets = {'name': forms.TextInput(attrs={'class': 'form-control'})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in ['group', 'year', 'academic_year']:
            self.fields[f].widget.attrs['class'] = 'form-select'


class AcademicYearForm(forms.ModelForm):
    class Meta:
        model = AcademicYear
        fields = ['name', 'start_date', 'end_date', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'start_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'end_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }
