from django.contrib.auth.models import AbstractUser, UserManager
from django.db import models


class SOSUserManager(UserManager):
    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault("role", "admin")  # superusers are platform admins
        return super().create_superuser(username, email, password, **extra_fields)


class User(AbstractUser):
    """Custom user with a role. Every person in the system is one of these."""

    class Role(models.TextChoices):
        RESIDENT = "resident", "Resident"
        GUARDIAN = "guardian", "Guardian"
        VOLUNTEER = "volunteer", "Volunteer"
        SECURITY = "security", "Security Staff"
        MANAGER = "manager", "Society Manager"   # RWA secretary: approves join requests
        ADMIN = "admin", "Admin"

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.RESIDENT)
    # Sandbox / public-demo accounts are deleted automatically after expires_at
    is_sandbox = models.BooleanField(default=False)
    expires_at = models.DateTimeField(null=True, blank=True)
    phone = models.CharField(max_length=15, unique=True, null=True, blank=True)
    is_phone_verified = models.BooleanField(default=False)

    # Volunteers only: can they take incidents right now?
    is_available = models.BooleanField(default=False)

    objects = SOSUserManager()

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"
