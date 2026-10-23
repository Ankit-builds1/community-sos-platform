from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from .models import Incident
from .services import run_due_escalations


@shared_task(ignore_result=True)
def run_escalations_task():
    """Scheduled by Celery beat every 10 s (see CELERY_BEAT_SCHEDULE)."""
    return run_due_escalations()


@shared_task(ignore_result=True)
def cleanup_demo_data_task():
    """Public demo only: delete incidents older than DEMO_RETENTION_HOURS, so the board
    stays readable and visitors' test messages don't pile up. No-op outside demo mode."""
    from community.services import cleanup_expired_sandboxes
    cleanup_expired_sandboxes()  # expired sandbox societies/users, in every mode
    if not settings.DEMO_MODE:
        return 0
    cutoff = timezone.now() - timedelta(hours=settings.DEMO_RETENTION_HOURS)
    deleted, _ = Incident.objects.filter(created_at__lt=cutoff).delete()
    return deleted
