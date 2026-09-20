from django.core.management.base import BaseCommand
from marks.models import ExamCategory

DEFAULT_CATEGORIES = [
    {'name': 'JEE-MAIN', 'bg_color': '#dbeafe', 'text_color': '#1e40af', 'icon': 'bi-calculator-fill'},
    {'name': 'IPE-MEC', 'bg_color': '#fef3c7', 'text_color': '#92400e', 'icon': 'bi-journal-bookmark-fill'},
    {'name': 'IPE-CEC', 'bg_color': '#e0e7ff', 'text_color': '#3730a3', 'icon': 'bi-book-half'},
    {'name': 'IPE-MPC', 'bg_color': '#dcfce7', 'text_color': '#166534', 'icon': 'bi-mortarboard-fill'},
    {'name': 'NEET', 'bg_color': '#fce7f3', 'text_color': '#9d174d', 'icon': 'bi-heart-pulse-fill'},
    {'name': 'IPE-BPC', 'bg_color': '#fae8ff', 'text_color': '#86198f', 'icon': 'bi-virus'},
]

class Command(BaseCommand):
    help = 'Seeds initial exam categories: JEE-MAIN, IPE-MEC, IPE-CEC, IPE-MPC, NEET, IPE-BPC'

    def handle(self, *args, **options):
        created_count = 0
        for cat_data in DEFAULT_CATEGORIES:
            cat, created = ExamCategory.objects.get_or_create(
                name=cat_data['name'],
                defaults={
                    'bg_color': cat_data['bg_color'],
                    'text_color': cat_data['text_color'],
                    'icon': cat_data['icon'],
                }
            )
            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f"Created category: {cat.name}"))
            else:
                self.stdout.write(f"Category already exists: {cat.name}")

        self.stdout.write(self.style.SUCCESS(f"Completed seeding categories. Newly created: {created_count}"))
