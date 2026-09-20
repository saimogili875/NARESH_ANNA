from django.core.management.base import BaseCommand
from django.utils import timezone
from accounts.models import AcademicYear, Group, Section
from students.models import Student


class Command(BaseCommand):
    help = "Seeds idempotent test Section and Student records for testing WhatsApp attendance flow safely."

    def add_arguments(self, parser):
        parser.add_argument(
            '--phone',
            type=str,
            default='9999999999',
            help='Target phone number for all test students (default: 9999999999).',
        )
        parser.add_argument(
            '--count',
            type=int,
            default=6,
            help='Number of test students to seed (default: 6).',
        )
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Delete existing test section & test students and recreate them fresh.',
        )

    def handle(self, *args, **options):
        phone = options['phone'].strip()
        count = options['count']
        reset = options['reset']

        self.stdout.write(self.style.SUCCESS("=" * 65))
        self.stdout.write(self.style.SUCCESS("  Sri NRI Junior College — Test Data Seeder"))
        self.stdout.write(self.style.SUCCESS(f"  Target Phone Number: {phone}"))
        self.stdout.write(self.style.SUCCESS(f"  Student Count: {count}"))
        self.stdout.write(self.style.SUCCESS(f"  Reset Mode: {reset}"))
        self.stdout.write(self.style.SUCCESS("=" * 65))

        # 1. Get or create active Academic Year
        today = timezone.localdate()
        academic_year, _ = AcademicYear.objects.get_or_create(
            name="2024-2025",
            defaults={
                'is_active': True,
                'start_date': today.replace(month=6, day=1),
                'end_date': today.replace(year=today.year + 1, month=5, day=31),
            }
        )

        # 2. Get or create Test Group & Section
        group, _ = Group.objects.get_or_create(
            code="TEST",
            defaults={
                'name': "Test Group",
                'academic_year': academic_year,
                'subjects_text': "Test Subjects",
            }
        )

        section, created_sec = Section.objects.get_or_create(
            group=group,
            year="1",
            name="A",
            academic_year=academic_year,
        )

        if created_sec:
            self.stdout.write(self.style.SUCCESS(f"✔ Created Test Section: {section}"))
        else:
            self.stdout.write(f"ℹ Using existing Test Section: {section}")

        # 3. Handle Reset if requested
        if reset:
            deleted_count, _ = Student.objects.filter(admission_number__startswith="TEST-STUDENT-").delete()
            self.stdout.write(self.style.WARNING(f"Cleared {deleted_count} existing test student record(s)."))

        # 4. Seed / Update Test Students
        created_students = 0
        updated_students = 0

        for i in range(1, count + 1):
            adm_no = f"TEST-STUDENT-{i:02d}"
            name = f"Test Student {i}"

            student, created = Student.objects.update_or_create(
                admission_number=adm_no,
                defaults={
                    'name': name,
                    'father_name': "Test Parent",
                    'mobile': phone,
                    'second_mobile': phone,
                    'section': section,
                    'academic_year': academic_year,
                    'is_active': True,
                }
            )
            if created:
                created_students += 1
            else:
                updated_students += 1

        self.stdout.write(self.style.SUCCESS("\n" + "-" * 50))
        self.stdout.write(self.style.SUCCESS(f"✔ Test Seeder Complete!"))
        self.stdout.write(self.style.SUCCESS(f"  Section: {section} (ID: {section.id})"))
        self.stdout.write(self.style.SUCCESS(f"  Created: {created_students} new test students"))
        self.stdout.write(self.style.SUCCESS(f"  Updated: {updated_students} existing test students"))
        self.stdout.write(self.style.SUCCESS(f"  All mapped to phone: {phone}"))
        self.stdout.write(self.style.SUCCESS("-" * 50))
