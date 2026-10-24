import os
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.core.models import User


class LoginTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("admin", password="admin1234", is_superuser=True)

    def test_username_case_insensitive(self):
        r = self.client.post(reverse("login"), {"username": "Admin", "password": "admin1234"})
        self.assertEqual(r.status_code, 302)

    def test_password_is_case_sensitive(self):
        r = self.client.post(reverse("login"), {"username": "admin", "password": "Admin1234"})
        self.assertEqual(r.status_code, 200)

    def test_login_form_disables_autocapitalize(self):
        self.assertContains(self.client.get(reverse("login")), 'autocapitalize="none"', count=2)

    def test_codespaces_resets_admin_password(self):
        self.user.set_password("otra-clave")
        self.user.save()
        with mock.patch.dict(os.environ, {"CODESPACE_NAME": "x", "HRMS_ADMIN_USER": "admin", "HRMS_ADMIN_PASSWORD": "Admin1234!"}):
            call_command("inicializar", stdout=StringIO())
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("admin1234"))

    def test_outside_codespaces_password_not_touched(self):
        with mock.patch.dict(os.environ, {"HRMS_ADMIN_USER": "admin", "HRMS_ADMIN_PASSWORD": "otra"}):
            os.environ.pop("CODESPACE_NAME", None)
            call_command("inicializar", stdout=StringIO())
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("admin1234"))
