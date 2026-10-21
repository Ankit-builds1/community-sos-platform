from django.conf import settings
from django.db import models

User = settings.AUTH_USER_MODEL


class Incident(models.Model):
    """One SOS raised by a resident. Lifecycle: Open -> Active -> Escalated -> Resolved -> Closed."""

    class Category(models.TextChoices):
        MEDICAL = "medical", "Medical"
        FALL = "fall", "Fall"
        FIRE = "fire", "Fire"
        SECURITY = "security", "Security threat"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        OPEN = "open", "Open"              # raised, nobody accepted yet
        ACTIVE = "active", "Active"        # a responder accepted
        ESCALATED = "escalated", "Escalated"  # nobody answered in time
        RESOLVED = "resolved", "Resolved"  # help given
        CLOSED = "closed", "Closed"        # report done, archived

    class Severity(models.TextChoices):  # filled by the AI triage agent later
        CRITICAL = "critical", "Critical"
        HIGH = "high", "High"
        MEDIUM = "medium", "Medium"
        LOW = "low", "Low"

    resident = models.ForeignKey(User, on_delete=models.CASCADE, related_name="incidents")
    society = models.ForeignKey("community.Society", on_delete=models.SET_NULL, null=True,
                                related_name="incidents")
    flat = models.ForeignKey("community.Flat", on_delete=models.SET_NULL, null=True, blank=True)

    category = models.CharField(max_length=20, choices=Category.choices, default=Category.OTHER)
    message = models.TextField(blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    severity = models.CharField(max_length=20, choices=Severity.choices, blank=True)

    # filled by the AI triage agent (runs AFTER alerts are sent)
    guardian_summary = models.CharField(max_length=255, blank=True)
    triage_confidence = models.FloatField(null=True, blank=True)
    triage_source = models.CharField(max_length=10, blank=True)  # "llm" or "rules"
    injection_suspected = models.BooleanField(default=False)
    triaged_at = models.DateTimeField(null=True, blank=True)
    escalation_level = models.PositiveSmallIntegerField(default=1)  # 1 = primary guardian
    last_escalated_at = models.DateTimeField(auto_now_add=True)  # when the current level began
    needs_human_review = models.BooleanField(default=False)  # max level reached, nobody came
    assigned_responder = models.ForeignKey(User, on_delete=models.SET_NULL, null=True,
                                           blank=True, related_name="assigned_incidents")

    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"SOS #{self.pk} {self.get_category_display()} by {self.resident} [{self.status}]"


class Alert(models.Model):
    """One notification sent to one person about an incident. Lets us track delivery & response."""

    class Audience(models.TextChoices):
        GUARDIAN = "guardian", "Guardian"
        SECURITY = "security", "Security"
        VOLUNTEER = "volunteer", "Volunteer"
        COMMUNITY = "community", "Community"
        EMERGENCY_CONTACT = "emergency_contact", "Emergency contact"

    class Channel(models.TextChoices):
        PUSH = "push", "Push"
        SMS = "sms", "SMS"
        EMAIL = "email", "Email"
        IN_APP = "in_app", "In-app"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"
        ACCEPTED = "accepted", "Accepted"
        DECLINED = "declined", "Declined"

    incident = models.ForeignKey(Incident, on_delete=models.CASCADE, related_name="alerts")
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True,
                                  related_name="alerts")
    # for emergency contacts who have no account
    recipient_phone = models.CharField(max_length=15, blank=True)
    audience = models.CharField(max_length=20, choices=Audience.choices)
    channel = models.CharField(max_length=10, choices=Channel.choices, default=Channel.IN_APP)
    escalation_level = models.PositiveSmallIntegerField(default=1)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        who = self.recipient or self.recipient_phone
        return f"Alert to {who} ({self.audience}/{self.channel}) - {self.status}"
