from django.conf import settings
from django.db import models

User = settings.AUTH_USER_MODEL


# ---------- Society -> Tower -> Flat ----------

class Society(models.Model):
    name = models.CharField(max_length=150)
    address = models.TextField()
    city = models.CharField(max_length=80)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "societies"

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
