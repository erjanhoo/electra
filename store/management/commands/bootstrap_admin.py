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

    @staticmethod
    def _generate_unique_username(User, preferred: str, exclude_pk=None) -> str:
        base = (preferred or 'admin')[:150]
        candidate = base
        counter = 2

        def exists(value: str) -> bool:
            queryset = User.objects.filter(username=value)
            if exclude_pk is not None:
                queryset = queryset.exclude(pk=exclude_pk)
            return queryset.exists()

        while exists(candidate):
            suffix = f'-{counter}'
            candidate = f"{base[:150 - len(suffix)]}{suffix}"
            counter += 1

        return candidate

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
        user = User.objects.filter(email__iexact=email).order_by('id').first()
        created = False

        if not user:
            username = self._generate_unique_username(User, email)
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name,
                is_staff=True,
                is_superuser=True,
                is_active=True,
            )
            created = True

        update_fields: set[str] = set()

        if user.email != email:
            user.email = email
            update_fields.add('email')

        if not user.username:
            user.username = self._generate_unique_username(User, email, exclude_pk=user.pk)
            update_fields.add('username')

        if not user.is_active:
            user.is_active = True
            update_fields.add('is_active')

        if not user.is_staff:
            user.is_staff = True
            update_fields.add('is_staff')

        if not user.is_superuser:
            user.is_superuser = True
            update_fields.add('is_superuser')

        if first_name and user.first_name != first_name:
            user.first_name = first_name
            update_fields.add('first_name')

        if last_name and user.last_name != last_name:
            user.last_name = last_name
            update_fields.add('last_name')

        password_synced = False
        if created or reset_password or not user.has_usable_password() or not user.check_password(password):
            user.set_password(password)
            update_fields.add('password')
            password_synced = True

        if update_fields:
            user.save(update_fields=sorted(update_fields))

        if created:
            self.stdout.write(self.style.SUCCESS(f'Created bootstrap admin account: {email}'))
        elif password_synced:
            self.stdout.write(self.style.SUCCESS(f'Updated bootstrap admin account and synchronized password: {email}'))
        else:
            self.stdout.write(self.style.SUCCESS(f'Verified bootstrap admin account: {email}'))
