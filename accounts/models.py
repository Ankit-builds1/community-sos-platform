from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Custom user with a role. Every person in the system is one of these."""

    class Role(models.TextChoices):
        RESIDENT = "resident", "Resident"
        GUARDIAN = "guardian", "Guardian"
        VOLUNTEER = "volunteer", "Volunteer"
        SECURITY = "security", "Security Staff"
        ADMIN = "admin", "Admin"

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.RESIDENT)
    phone = models.CharField(max_length=15, unique=True, null=True, blank=True)
    is_phone_verified = models.BooleanField(default=False)

    # Volunteers only: can they take incidents right now?
    is_available = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"
