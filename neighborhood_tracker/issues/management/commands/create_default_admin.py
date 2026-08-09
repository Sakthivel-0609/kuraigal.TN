"""
Creates a default superuser if one doesn't already exist - used as a one-time
bootstrap step on platforms like Render that don't offer shell access on the
free tier, so `createsuperuser` (interactive) can't be run directly.

Usage: python manage.py create_default_admin

Reads credentials from environment variables when available, with safe
fallbacks - override ADMIN_USERNAME / ADMIN_EMAIL / ADMIN_PASSWORD in Render's
environment variables for a private password instead of the default below.
"""
import os
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Creates a default superuser if none exists yet (safe to run on every deploy)."

    def handle(self, *args, **options):
        username = os.environ.get('ADMIN_USERNAME', 'admin')
        email = os.environ.get('ADMIN_EMAIL', 'admin@example.com')
        password = os.environ.get('ADMIN_PASSWORD', 'Kuraigal@2026')

        if User.objects.filter(username=username).exists():
            self.stdout.write(self.style.WARNING(f"User '{username}' already exists - skipping."))
            return

        User.objects.create_superuser(username=username, email=email, password=password)
        self.stdout.write(self.style.SUCCESS(f"Superuser '{username}' created successfully."))
