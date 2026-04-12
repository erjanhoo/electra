from django.conf import settings
from rest_framework.permissions import BasePermission


def is_admin_user(user):
    if not user or not user.is_authenticated:
        return False

    if user.is_staff or user.is_superuser:
        return True

    admin_emails = {email.strip().lower() for email in getattr(settings, 'ADMIN_EMAILS', ()) if email}
    user_email = (user.email or '').strip().lower()
    return bool(user_email) and user_email in admin_emails


class IsAdminAccount(BasePermission):
    message = 'Admin access required.'

    def has_permission(self, request, view):
        return is_admin_user(request.user)
