import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {'1', 'true', 'yes', 'on'}


class Command(BaseCommand):
    help = 'Create or update a bootstrap admin user from environment variables.'

    def handle(self, *args, **options):
        email = os.getenv('ELECTRA_BOOTSTRAP_ADMIN_EMAIL', '').strip().lower()
        password = os.getenv('ELECTRA_BOOTSTRAP_ADMIN_PASSWORD', '').strip()
        first_name = os.getenv('ELECTRA_BOOTSTRAP_ADMIN_FIRST_NAME', '').strip()
        last_name = os.getenv('ELECTRA_BOOTSTRAP_ADMIN_LAST_NAME', '').strip()
        reset_password = env_bool('ELECTRA_BOOTSTRAP_ADMIN_RESET_PASSWORD', default=False)

        if not email or not password:
            self.stdout.write(
                self.style.WARNING(
                    'Skipping bootstrap admin: set ELECTRA_BOOTSTRAP_ADMIN_EMAIL and ELECTRA_BOOTSTRAP_ADMIN_PASSWORD.'
                )
            )
            return

        User = get_user_model()
        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                'username': email,
                'first_name': first_name,
                'last_name': last_name,
                'is_staff': True,
                'is_superuser': True,
            },
        )

        update_fields: list[str] = []

        if not user.username:
            user.username = email
            update_fields.append('username')

        if not user.is_staff:
            user.is_staff = True
            update_fields.append('is_staff')

        if not user.is_superuser:
            user.is_superuser = True
            update_fields.append('is_superuser')

        if first_name and user.first_name != first_name:
            user.first_name = first_name
            update_fields.append('first_name')

        if last_name and user.last_name != last_name:
            user.last_name = last_name
            update_fields.append('last_name')

        if created or reset_password:
            user.set_password(password)
            update_fields.append('password')

        if update_fields:
            user.save(update_fields=update_fields)

        if created:
            self.stdout.write(self.style.SUCCESS(f'Created bootstrap admin account: {email}'))
        elif reset_password:
            self.stdout.write(self.style.SUCCESS(f'Updated bootstrap admin account and reset password: {email}'))
        else:
            self.stdout.write(self.style.SUCCESS(f'Verified bootstrap admin account: {email}'))
