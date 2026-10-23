import secrets

from django.conf import settings
from django.db import models

User = settings.AUTH_USER_MODEL

# No 0/O/1/I so codes are easy to read off a notice board
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def new_code(length=6):
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(length))


# ---------- Society -> Tower -> Flat ----------

class Society(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending approval"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    name = models.CharField(max_length=150)
    address = models.TextField()
    city = models.CharField(max_length=80)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # Self-service onboarding
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.APPROVED)
    join_code = models.CharField(max_length=12, unique=True, null=True, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name="societies_created")
    is_sandbox = models.BooleanField(default=False)      # deleted after expires_at
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name_plural = "societies"

    def ensure_join_code(self):
        """Give the society a unique join code (created on first use)."""
        if not self.join_code:
            code = new_code()
            while Society.objects.filter(join_code=code).exists():
                code = new_code()
            self.join_code = code
            self.save(update_fields=["join_code"])
        return self.join_code

    def __str__(self):
        return self.name


class Tower(models.Model):
    society = models.ForeignKey(Society, on_delete=models.CASCADE, related_name="towers")
    name = models.CharField(max_length=50)  # e.g. "Block B"

    class Meta:
        unique_together = ("society", "name")

    def __str__(self):
        return f"{self.society.name} - {self.name}"


class Flat(models.Model):
    tower = models.ForeignKey(Tower, on_delete=models.CASCADE, related_name="flats")
    number = models.CharField(max_length=20)  # e.g. "402"
    floor = models.PositiveSmallIntegerField(default=0)

    class Meta:
        unique_together = ("tower", "number")

    def __str__(self):
        return f"{self.tower} / {self.number}"


class Residency(models.Model):
    """Links a user (resident, volunteer, security) to a flat or society."""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="residency")
    society = models.ForeignKey(Society, on_delete=models.CASCADE, related_name="members")
    flat = models.ForeignKey(Flat, on_delete=models.SET_NULL, null=True, blank=True,
                             related_name="residents")

    class Meta:
        verbose_name_plural = "residencies"

    def __str__(self):
        return f"{self.user} @ {self.flat or self.society}"


# ---------- Guardians & emergency contacts ----------

class GuardianLink(models.Model):
    """A guardian who gets alerted when this resident raises an SOS.
    priority 1 = primary guardian, 2 = secondary, and so on (escalation order)."""
    resident = models.ForeignKey(User, on_delete=models.CASCADE, related_name="guardians")
    guardian = models.ForeignKey(User, on_delete=models.CASCADE, related_name="wards")
    priority = models.PositiveSmallIntegerField(default=1)
    relation = models.CharField(max_length=50, blank=True)  # e.g. "Son"

    class Meta:
        unique_together = ("resident", "guardian")
        ordering = ["resident", "priority"]

    def __str__(self):
        return f"{self.guardian} -> {self.resident} (P{self.priority})"


class EmergencyContact(models.Model):
    """Someone outside the app (no account) - reached by SMS/call at the last escalation level."""
    resident = models.ForeignKey(User, on_delete=models.CASCADE,
                                 related_name="emergency_contacts")
    name = models.CharField(max_length=100)
    phone = models.CharField(max_length=15)
    relation = models.CharField(max_length=50, blank=True)
    is_verified = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.name} ({self.phone}) for {self.resident}"


# ---------- Self-service onboarding ----------

class JoinRequest(models.Model):
    """A user asks to join a society (via its join code). The society manager decides."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    ROLE_CHOICES = [("resident", "Resident"), ("volunteer", "Volunteer"),
                    ("security", "Security Staff")]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="join_requests")
    society = models.ForeignKey(Society, on_delete=models.CASCADE, related_name="join_requests")
    flat = models.ForeignKey(Flat, on_delete=models.SET_NULL, null=True, blank=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="resident")
    note = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    decided_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name="join_decisions")
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user} -> {self.society} ({self.status})"


class GuardianInvite(models.Model):
    """A resident shares this link; whoever accepts it becomes their guardian."""
    resident = models.ForeignKey(User, on_delete=models.CASCADE,
                                 related_name="guardian_invites")
    token = models.CharField(max_length=64, unique=True, default=secrets.token_urlsafe)
    priority = models.PositiveSmallIntegerField(default=1)
    relation = models.CharField(max_length=50, blank=True)
    accepted_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name="accepted_invites")
    created_at = models.DateTimeField(auto_now_add=True)
    accepted_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Invite from {self.resident} (P{self.priority})"
