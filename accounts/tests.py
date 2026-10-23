from django.test import TestCase

from .models import User


class UserTests(TestCase):

    def test_superuser_gets_admin_role(self):
        user = User.objects.create_superuser("boss", "b@x.com", "pass12345!")
        self.assertEqual(user.role, User.Role.ADMIN)

    def test_normal_user_defaults_to_resident(self):
        self.assertEqual(User.objects.create_user("r", password="pass12345!").role,
                         User.Role.RESIDENT)
