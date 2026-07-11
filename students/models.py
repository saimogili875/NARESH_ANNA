from django.db import models
from accounts.models import Section, AcademicYear


class Student(models.Model):
    admission_number = models.CharField(max_length=20, unique=True)
    hall_ticket_number = models.CharField(max_length=20, blank=True)
    name = models.CharField(max_length=100)
    father_name = models.CharField(max_length=100)
    mother_name = models.CharField(max_length=100, blank=True)
    mobile = models.CharField(max_length=15)
    second_mobile = models.CharField(max_length=15, blank=True, help_text='Secondary contact number (parent/guardian)')
    third_mobile = models.CharField(max_length=15, blank=True, help_text='Third contact number')
    fourth_mobile = models.CharField(max_length=15, blank=True, help_text='Fourth contact number')
    apaar_id = models.CharField(max_length=20, blank=True, verbose_name='APAAR ID',
        help_text='Academic Bank of Credits ID — see apaar.education.gov.in')
    sport = models.CharField(max_length=100, blank=True, help_text='Sport activity / event the student participates in')
    aadhaar = models.CharField(max_length=12, blank=True)
    address = models.TextField(blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    photo = models.ImageField(upload_to='students/photos/', blank=True, null=True)

    # Previous school info
    prev_school_name = models.CharField(max_length=150, blank=True, verbose_name='Previous School Name')
    prev_school_location = models.CharField(max_length=150, blank=True, verbose_name='School Location')
    marks_telugu = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, verbose_name='Telugu')
    marks_hindi = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, verbose_name='Hindi')
    marks_english = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, verbose_name='English')
    marks_maths = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, verbose_name='Maths')
    marks_physics = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, verbose_name='Physics')
    marks_biology = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, verbose_name='Biology')
    marks_social = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, verbose_name='Social')
    marks_total = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True, verbose_name='Total Marks')

    # CASCADE (not SET_NULL): deleting a Section, Group, or Academic Year must
    # permanently remove every student that belonged to it — no orphaned
    # student rows left behind with a blank section/year.
    section = models.ForeignKey(Section, on_delete=models.CASCADE, null=True, related_name='students')
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, null=True)
    date_of_admission = models.DateField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.admission_number} - {self.name}"

    @property
    def year(self):
        return self.section.year if self.section else None

    @property
    def group(self):
        return self.section.group if self.section else None
