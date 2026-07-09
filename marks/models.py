from django.db import models
from students.models import Student
from accounts.models import AcademicYear, Group


class Subject(models.Model):
    name = models.CharField(max_length=100, unique=True)
    class Meta:
        verbose_name_plural = "1. Subjects"

    def __str__(self):
        return self.name


class ExamType(models.Model):
    name = models.CharField(max_length=100, unique=True)
    class Meta:
        verbose_name_plural = "4. Exam Types"

    def __str__(self):
        return self.name


class ExamCategory(models.Model):
    name = models.CharField(max_length=100, unique=True)
    bg_color = models.CharField(max_length=20, default="#f3f4f6")
    text_color = models.CharField(max_length=20, default="#374151")
    icon = models.CharField(max_length=50, default="bi-book")
    is_fixed_marks = models.BooleanField(default=False)
    subjects = models.ManyToManyField(Subject, blank=True)
    
    class Meta:
        verbose_name_plural = "2. Exam Categories"
        
    def __str__(self):
        return self.name


class GroupCategoryConfig(models.Model):
    group = models.ForeignKey(Group, on_delete=models.CASCADE)
    category = models.ForeignKey(ExamCategory, on_delete=models.CASCADE)
    
    class Meta:
        unique_together = ['group', 'category']
        verbose_name_plural = "3. Connect Category to Group"
        
    def __str__(self):
        return f"{self.group} - {self.category}"


class Exam(models.Model):
    exam_type = models.ForeignKey(ExamType, on_delete=models.CASCADE)
    custom_name = models.CharField(max_length=100, blank=True, help_text='Only for Custom Exam type')
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE)
    group = models.ForeignKey(
        Group, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='exams',
        help_text='Student group (MPIC / BPIC / CEC / MEC) this exam is for.'
    )
    category = models.ForeignKey(
        ExamCategory, on_delete=models.CASCADE,
        help_text='Decides which subjects appear on the marks entry screen.'
    )
    date = models.DateField()
    max_marks = models.IntegerField(default=100)

    def display_name(self):
        if self.exam_type.name.lower() == 'custom' and self.custom_name:
            return self.custom_name
        return self.exam_type.name

    def is_fixed_marks(self):
        return self.category.is_fixed_marks

    def __str__(self):
        return f"{self.display_name()} - {self.academic_year}"


class ExamSubjectMaxMark(models.Model):
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='subject_max_marks')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    max_marks = models.IntegerField(default=100)

    class Meta:
        unique_together = ['exam', 'subject']

    def __str__(self):
        return f"{self.exam} - {self.subject}: {self.max_marks}"


class Mark(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='marks')
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='marks')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    marks_obtained = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    is_absent = models.BooleanField(default=False)

    class Meta:
        unique_together = ['student', 'exam', 'subject']

    def __str__(self):
        return f"{self.student.name} - {self.exam} - {self.subject}: {self.marks_obtained}"
