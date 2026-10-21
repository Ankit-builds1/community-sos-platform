"""Business logic for raising an SOS and deciding who gets alerted.

Kept out of views so the same code can later be called from Celery workers,
the voice SOS endpoint and the AI triage agent.
"""
import logging
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from accounts.models import User
from community.models import EmergencyContact, GuardianLink

from .models import Alert, Incident

logger = logging.getLogger(__name__)


@transaction.atomic
def raise_sos(resident, *, category="other", message="", latitude=None, longitude=None):
    """Create the incident and the level-1 alerts. Always runs before any AI step."""
    residency = getattr(resident, "residency", None)
    incident = Incident.objects.create(
        resident=resident,
        society=residency.society if residency else None,
        flat=residency.flat if residency else None,
        category=category,
        message=message,
        latitude=latitude,
        longitude=longitude,
    )
    alerts = build_level_one_alerts(incident)
    Alert.objects.bulk_create(alerts)
    for alert in incident.alerts.all():
        send_alert(alert)
    return incident


def build_level_one_alerts(incident):
    """Level 1 = primary guardian + security staff + available volunteers of the society."""
    alerts = []

    primary = (GuardianLink.objects.filter(resident=incident.resident)
               .order_by("priority").select_related("guardian").first())
    if primary:
        alerts.append(Alert(incident=incident, recipient=primary.guardian,
                            audience=Alert.Audience.GUARDIAN, channel=Alert.Channel.PUSH))

    if incident.society_id:
        society_people = User.objects.filter(residency__society_id=incident.society_id)

        for guard in society_people.filter(role=User.Role.SECURITY):
            alerts.append(Alert(incident=incident, recipient=guard,
                                audience=Alert.Audience.SECURITY, channel=Alert.Channel.PUSH))

        volunteers = society_people.filter(role=User.Role.VOLUNTEER, is_available=True)
        for vol in volunteers.exclude(pk=incident.resident_id):
            alerts.append(Alert(incident=incident, recipient=vol,
                                audience=Alert.Audience.VOLUNTEER, channel=Alert.Channel.PUSH))
    return alerts


def send_alert(alert):
    """Placeholder sender. Real push (FCM) / SMS (Twilio/MSG91) / email come next.
    For now it just logs and marks the alert as sent."""
    logger.warning("ALERT -> %s | incident #%s | %s", alert.recipient or alert.recipient_phone,
                   alert.incident_id, alert.get_audience_display())
    alert.status = Alert.Status.SENT
    alert.save(update_fields=["status"])


# ---------------- Responder actions ----------------

class SOSActionError(Exception):
    """Raised when an action is not allowed (e.g. incident already taken)."""


@transaction.atomic
def accept_incident(incident, user):
    """A guardian / volunteer / security taps 'Accept'. First one wins."""
    incident = Incident.objects.select_for_update().get(pk=incident.pk)
    if incident.status not in (Incident.Status.OPEN, Incident.Status.ESCALATED):
        raise SOSActionError(f"Incident is already {incident.status}.")
    alert = incident.alerts.filter(recipient=user).first()
    if alert is None and not user.is_staff:
        raise SOSActionError("You were not alerted for this incident.")

    incident.status = Incident.Status.ACTIVE
    incident.assigned_responder = user
    incident.needs_human_review = False
    incident.save(update_fields=["status", "assigned_responder", "needs_human_review"])
    if alert:
        alert.status = Alert.Status.ACCEPTED
        alert.responded_at = timezone.now()
        alert.save(update_fields=["status", "responded_at"])
    return incident


def decline_incident(incident, user):
    alert = incident.alerts.filter(recipient=user).first()
    if alert is None:
        raise SOSActionError("You were not alerted for this incident.")
    alert.status = Alert.Status.DECLINED
    alert.responded_at = timezone.now()
    alert.save(update_fields=["status", "responded_at"])
    return incident


def resolve_incident(incident, user):
    """The assigned responder, security, the resident themself or an admin marks it resolved."""
    allowed = (user == incident.assigned_responder or user == incident.resident
               or user.role == User.Role.SECURITY or user.is_staff)
    if not allowed:
        raise SOSActionError("You cannot resolve this incident.")
    if incident.status in (Incident.Status.RESOLVED, Incident.Status.CLOSED):
        raise SOSActionError(f"Incident is already {incident.status}.")
    incident.status = Incident.Status.RESOLVED
    incident.resolved_at = timezone.now()
    incident.save(update_fields=["status", "resolved_at"])
    return incident


# ---------------- Escalation ----------------
#   Level 1: primary guardian + security + available volunteers   (sent by raise_sos)
#   Level 2: secondary guardian(s)  (priority 2)
#   Level 3: remaining guardians + emergency contacts by SMS
#   After level 3: flag for human review and re-alert security (human in the loop)

MAX_LEVEL = 3


def escalation_timeout():
    return timedelta(seconds=getattr(settings, "SOS_ESCALATION_TIMEOUT_SECONDS", 120))


def build_alerts_for_level(incident, level):
    links = GuardianLink.objects.filter(resident=incident.resident).select_related("guardian")
    alerts = []
    if level == 2:
        for link in links.filter(priority=2):
            alerts.append(Alert(incident=incident, recipient=link.guardian, escalation_level=2,
                                audience=Alert.Audience.GUARDIAN, channel=Alert.Channel.PUSH))
    elif level == 3:
        for link in links.filter(priority__gte=3):
            alerts.append(Alert(incident=incident, recipient=link.guardian, escalation_level=3,
                                audience=Alert.Audience.GUARDIAN, channel=Alert.Channel.PUSH))
        for contact in EmergencyContact.objects.filter(resident=incident.resident):
            alerts.append(Alert(incident=incident, recipient_phone=contact.phone,
                                escalation_level=3, channel=Alert.Channel.SMS,
                                audience=Alert.Audience.EMERGENCY_CONTACT))
    return alerts


@transaction.atomic
def escalate_incident(incident):
    """Move an unanswered incident one level up. Returns True if something changed."""
    incident = Incident.objects.select_for_update().get(pk=incident.pk)
    if incident.status not in (Incident.Status.OPEN, Incident.Status.ESCALATED):
        return False  # someone accepted or it was resolved meanwhile

    now = timezone.now()
    if incident.escalation_level >= MAX_LEVEL:
        if not incident.needs_human_review:
            incident.needs_human_review = True
            incident.last_escalated_at = now
            incident.save(update_fields=["needs_human_review", "last_escalated_at"])
            logger.warning("HUMAN REVIEW NEEDED -> incident #%s: nobody responded", incident.pk)
            return True
        return False

    incident.escalation_level += 1
    incident.status = Incident.Status.ESCALATED
    incident.last_escalated_at = now
    incident.save(update_fields=["escalation_level", "status", "last_escalated_at"])

    new_alerts = Alert.objects.bulk_create(build_alerts_for_level(incident, incident.escalation_level))
    for alert in new_alerts:
        send_alert(alert)
    logger.warning("ESCALATED incident #%s to level %s (%s new alerts)",
                   incident.pk, incident.escalation_level, len(new_alerts))
    return True


def run_due_escalations():
    """Escalate every unanswered incident whose current level has timed out.
    Called by the `run_escalations` command now; by a Celery beat task later."""
    cutoff = timezone.now() - escalation_timeout()
    due = Incident.objects.filter(
        status__in=[Incident.Status.OPEN, Incident.Status.ESCALATED],
        last_escalated_at__lte=cutoff,
    )
    return sum(1 for incident in due if escalate_incident(incident))
