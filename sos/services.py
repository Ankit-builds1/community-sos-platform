"""Business logic for raising an SOS and deciding who gets alerted.

Kept out of views so the same code can later be called from Celery workers,
the voice SOS endpoint and the AI triage agent.
"""
import logging

from django.db import transaction

from accounts.models import User
from community.models import GuardianLink

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
