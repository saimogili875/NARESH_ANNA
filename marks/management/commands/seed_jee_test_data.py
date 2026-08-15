from datetime import date
from django.core.management.base import BaseCommand
from django.utils import timezone
from accounts.models import User, AcademicYear, Group, Section
from students.models import Student
from faculty.models import Faculty
from marks.models import Subject, ExamType, ExamCategory, GroupCategoryConfig, Exam, ExamSubjectMaxMark, Mark


class Command(BaseCommand):
    help = "Seeds a full JEE Main test scenario idempotently (Section, 5 Students, JEE Exam, Marks, and Faculty user)."

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Deletes test students (TEST-JEE-*) and their Marks before reseeding.',
        )

    def handle(self, *args, **options):
        reset = options['reset']
        today = timezone.localdate()

        self.stdout.write(self.style.SUCCESS("=" * 65))
        self.stdout.write(self.style.SUCCESS("  Sri NRI Junior College — JEE Main Test Data Seeder"))
        self.stdout.write(self.style.SUCCESS(f"  Reset Mode: {reset}"))
        self.stdout.write(self.style.SUCCESS("=" * 65))

        # 0. Handle Reset if requested
        if reset:
            deleted_marks, _ = Mark.objects.filter(student__admission_number__startswith="TEST-JEE-").delete()
            deleted_students, _ = Student.objects.filter(admission_number__startswith="TEST-JEE-").delete()
            self.stdout.write(self.style.WARNING(
                f"Cleared {deleted_students} test student(s) and {deleted_marks} mark record(s)."
            ))

        # 1. Get or create active AcademicYear
        academic_year = AcademicYear.objects.filter(is_active=True).first()
        if not academic_year:
            academic_year, _ = AcademicYear.objects.get_or_create(
                name="2025-2026",
                defaults={
                    'is_active': True,
                    'start_date': date(today.year if today.month >= 6 else today.year - 1, 6, 1),
                    'end_date': date((today.year + 1) if today.month >= 6 else today.year, 5, 31),
                }
            )
            self.stdout.write(self.style.SUCCESS(f"✔ Created Academic Year: {academic_year}"))
        else:
            self.stdout.write(f"ℹ Using active Academic Year: {academic_year}")

        # 2. Get or create Group & Section
        group, _ = Group.objects.get_or_create(
            code="MPC",
            defaults={
                'name': "MPC",
                'academic_year': academic_year,
                'subjects_text': "Maths, Physics, Chemistry",
            }
        )

        section, created_sec = Section.objects.get_or_create(
            group=group,
            year="1",
            name="A",
            academic_year=academic_year,
        )
        if created_sec:
            self.stdout.write(self.style.SUCCESS(f"✔ Created Section: {section}"))
        else:
            self.stdout.write(f"ℹ Using Section: {section}")

        # 3. Get or create JEE-relevant Subjects ("Physics", "Chemistry", "Maths" or "Mathematics")
        subject_names = ["Physics", "Chemistry", "Maths"]
        subjects = []
        for sname in subject_names:
            sub = Subject.objects.filter(name__iexact=sname).first()
            if not sub and sname == "Maths":
                sub = Subject.objects.filter(name__iexact="Mathematics").first()
            if not sub:
                sub, _ = Subject.objects.get_or_create(name=sname)
                self.stdout.write(self.style.SUCCESS(f"✔ Created Subject: {sub.name}"))
            else:
                self.stdout.write(f"ℹ Using Subject: {sub.name}")
            subjects.append(sub)

        # 4. Get or create ExamCategory "JEE Main"
        category = ExamCategory.objects.filter(name__iexact="JEE Main").first()
        if not category:
            category, _ = ExamCategory.objects.get_or_create(
                name="JEE Main",
                defaults={
                    'is_fixed_marks': True,
                    'bg_color': '#e0f2fe',
                    'text_color': '#0369a1',
                    'icon': 'bi-calculator',
                }
            )
            self.stdout.write(self.style.SUCCESS(f"✔ Created ExamCategory: {category.name}"))
        else:
            self.stdout.write(f"ℹ Using ExamCategory: {category.name}")

        category.subjects.add(*subjects)

        # 5. GroupCategoryConfig link
        config, config_created = GroupCategoryConfig.objects.get_or_create(
            group=group, category=category
        )
        if config_created:
            self.stdout.write(self.style.SUCCESS(f"✔ Connected Group ({group.code}) to Category ({category.name})"))

        # 6. ExamType & Exam
        exam_type, _ = ExamType.objects.get_or_create(name="Unit Test 1")
        exam, exam_created = Exam.objects.get_or_create(
            exam_type=exam_type,
            academic_year=academic_year,
            group=group,
            category=category,
            defaults={
                'date': today,
                'max_marks': 300,
                'custom_name': '',
            }
        )
        if exam_created:
            self.stdout.write(self.style.SUCCESS(f"✔ Created Exam: {exam.display_name()} ({category.name}) on {exam.date}"))
        else:
            self.stdout.write(f"ℹ Using Exam: {exam.display_name()} ({category.name})")

        for sub in subjects:
            ExamSubjectMaxMark.objects.update_or_create(
                exam=exam, subject=sub, defaults={'max_marks': 100}
            )

        # 7. Create 5 Students
        student_specs = [
            ("TEST-JEE-01", "Aarav Sharma", "Rajesh Sharma", "9876543210"),
            ("TEST-JEE-02", "Ananya Reddy", "Srinivas Reddy", "9876543211"),
            ("TEST-JEE-03", "Rohan Verma", "Suresh Verma", "9876543212"),
            ("TEST-JEE-04", "Sai Kiran", "Venkatesh Rao", "9876543213"),
            ("TEST-JEE-05", "Priya Nambiar", "Madhavan Nambiar", "9876543214"),
        ]

        created_students = 0
        updated_students = 0
        students_list = []

        for adm_no, name, father_name, mobile in student_specs:
            student, created = Student.objects.update_or_create(
                admission_number=adm_no,
                defaults={
                    'name': name,
                    'father_name': father_name,
                    'mobile': mobile,
                    'second_mobile': mobile,
                    'section': section,
                    'academic_year': academic_year,
                    'is_active': True,
                }
            )
            students_list.append(student)
            if created:
                created_students += 1
            else:
                updated_students += 1

        # 8. Create 3 Faculty Users & Profiles (One for each subject: Physics, Chemistry, Maths)
        faculty_specs = [
            ("faculty_physics", "FAC-JEE-01", "Dr. Vikram Rao", "Physics"),
            ("faculty_chemistry", "FAC-JEE-02", "Prof. Anitha Sharma", "Chemistry"),
            ("faculty_maths", "FAC-JEE-03", "Prof. Rajesh Kumar", "Maths"),
        ]

        created_faculty = []
        for username, emp_id, fac_name, sub_name in faculty_specs:
            user, _ = User.objects.get_or_create(
                username=username,
                defaults={
                    'role': User.ROLE_FACULTY,
                    'first_name': fac_name.split()[0],
                    'last_name': fac_name.split()[-1],
                    'email': f"{username}@college.edu",
                    'is_active': True,
                }
            )
            user.set_password("password123")
            user.save()

            faculty, _ = Faculty.objects.update_or_create(
                employee_id=emp_id,
                defaults={
                    'user': user,
                    'name': fac_name,
                    'subject': sub_name,
                    'phone': "9876543200",
                    'email': f"{username}@college.edu",
                    'date_of_joining': date(2023, 6, 1),
                    'is_active': True,
                }
            )
            faculty.assigned_sections.add(section)
            target_sub = next((s for s in subjects if s.name.lower() == sub_name.lower() or (sub_name.lower() == 'maths' and s.name.lower() in ['maths', 'mathematics'])), None)
            if target_sub:
                faculty.assigned_subjects.set([target_sub])
            created_faculty.append((username, "password123", fac_name, sub_name))

        # 9. Create Mark rows for all 5 students
        sample_scores = {
            "TEST-JEE-01": {"Physics": 85.0, "Chemistry": 78.5, "Maths": 92.0, "Mathematics": 92.0},
            "TEST-JEE-02": {"Physics": 72.0, "Chemistry": 81.0, "Maths": 79.5, "Mathematics": 79.5},
            "TEST-JEE-03": {"Physics": 90.5, "Chemistry": 88.0, "Maths": 95.0, "Mathematics": 95.0},
            "TEST-JEE-04": {"Physics": 64.0, "Chemistry": 70.0, "Maths": 68.5, "Mathematics": 68.5},
            "TEST-JEE-05": {"Physics": 77.5, "Chemistry": 83.5, "Maths": 86.0, "Mathematics": 86.0},
        }

        created_marks = 0
        updated_marks = 0

        for student in students_list:
            student_scores = sample_scores.get(student.admission_number, {})
            for sub in subjects:
                score = student_scores.get(sub.name, 75.0)
                mark, created = Mark.objects.update_or_create(
                    student=student,
                    exam=exam,
                    subject=sub,
                    defaults={
                        'marks_obtained': score,
                        'is_absent': False,
                    }
                )
                if created:
                    created_marks += 1
                else:
                    updated_marks += 1

        # Summary
        self.stdout.write(self.style.SUCCESS("\n" + "=" * 65))
        self.stdout.write(self.style.SUCCESS("✔ JEE Test Seeder Completed Successfully!"))
        self.stdout.write(self.style.SUCCESS(f"  • Section: {section} (Group: {group.code})"))
        self.stdout.write(self.style.SUCCESS(f"  • Exam: {exam.display_name()} - Category: {category.name} (Max Marks: {exam.max_marks})"))
        self.stdout.write(self.style.SUCCESS(f"  • Subjects: {', '.join(s.name for s in subjects)}"))
        self.stdout.write(self.style.SUCCESS(f"  • Students: {created_students} created, {updated_students} updated (Total: {len(students_list)})"))
        self.stdout.write(self.style.SUCCESS(f"  • Marks: {created_marks} created, {updated_marks} updated (Total: {created_marks + updated_marks})"))
        self.stdout.write(self.style.SUCCESS("-" * 65))
        self.stdout.write(self.style.SUCCESS("🔑 3 FACULTY LOGIN CREDENTIALS (1 SUBJECT EACH):"))
        self.stdout.write(self.style.SUCCESS("   1. PHYSICS FACULTY:"))
        self.stdout.write(self.style.SUCCESS("      Username: faculty_physics"))
        self.stdout.write(self.style.SUCCESS("      Password: password123"))
        self.stdout.write(self.style.SUCCESS("   2. CHEMISTRY FACULTY:"))
        self.stdout.write(self.style.SUCCESS("      Username: faculty_chemistry"))
        self.stdout.write(self.style.SUCCESS("      Password: password123"))
        self.stdout.write(self.style.SUCCESS("   3. MATHS FACULTY:"))
        self.stdout.write(self.style.SUCCESS("      Username: faculty_maths"))
        self.stdout.write(self.style.SUCCESS("      Password: password123"))
        self.stdout.write(self.style.SUCCESS("=" * 65 + "\n"))
