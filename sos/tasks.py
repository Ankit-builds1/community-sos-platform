from celery import shared_task

from .services import run_due_escalations


@shared_task(ignore_result=True)
def run_escalations_task():
    """Scheduled by Celery beat every 10 s (see CELERY_BEAT_SCHEDULE)."""
    return run_due_escalations()
