from celery import shared_task

from .service import triage_incident


@shared_task(ignore_result=True, autoretry_for=(Exception,), retry_backoff=2,
             max_retries=2)
def triage_incident_task(incident_id: int):
    """AI triage for one incident, run by a Celery worker.
    triage_incident() never raises (it falls back to rules), so retries only cover
    unexpected crashes such as the database being briefly unavailable."""
    triage_incident(incident_id)
