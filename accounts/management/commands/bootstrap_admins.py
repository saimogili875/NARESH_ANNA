import os
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

User = get_user_model()


class Command(BaseCommand):
    help = 'Idempotently create initial admin/superuser accounts from environment variables.'

    def handle(self, *args, **options):
        # Account 1
        admin1_user = os.environ.get('ADMIN1_USERNAME') or os.environ.get('ADMIN_USERNAME')
        admin1_pass = os.environ.get('ADMIN1_PASSWORD') or os.environ.get('ADMIN_PASSWORD')

        if admin1_user and admin1_pass:
            if not User.objects.filter(username=admin1_user).exists():
                User.objects.create_superuser(username=admin1_user, password=admin1_pass)
                self.stdout.write(self.style.SUCCESS(f'Superuser "{admin1_user}" created successfully.'))
            else:
                self.stdout.write(f'Superuser "{admin1_user}" already exists. Skipping.')

        # Account 2
        admin2_user = os.environ.get('ADMIN2_USERNAME')
        admin2_pass = os.environ.get('ADMIN2_PASSWORD')

        if admin2_user and admin2_pass:
            if not User.objects.filter(username=admin2_user).exists():
                User.objects.create_superuser(username=admin2_user, password=admin2_pass)
                self.stdout.write(self.style.SUCCESS(f'Superuser "{admin2_user}" created successfully.'))
            else:
                self.stdout.write(f'Superuser "{admin2_user}" already exists. Skipping.')
