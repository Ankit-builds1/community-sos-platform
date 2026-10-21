"""Connects the triage agent to incidents."""
import logging
import threading

from django.conf import settings
from django.db import close_old_connections
from django.utils import timezone

from sos.models import Incident

from .graph import run_triage

logger = logging.getLogger(__name__)


def triage_incident(incident_id: int):
    """Run the agent and store its result on the incident. Never raises."""
    try:
        incident = Incident.objects.get(pk=incident_id)
        state = run_triage(incident.message, incident.category)
        result = state["final"]

        incident.severity = result.severity
        incident.category = result.category
        incident.guardian_summary = result.guardian_summary
        incident.triage_confidence = result.confidence
        incident.triage_source = result.source
        incident.injection_suspected = result.injection_suspected
        incident.triaged_at = timezone.now()
        incident.save(update_fields=["severity", "category", "guardian_summary",
                                     "triage_confidence", "triage_source",
                                     "injection_suspected", "triaged_at"])
        logger.warning("TRIAGE incident #%s -> %s/%s via %s (conf %.2f, llm %sms)",
                       incident.pk, result.category, result.severity, result.source,
                       result.confidence, state.get("latency_ms", {}).get("llm"))
    except Exception:
        logger.exception("Triage crashed for incident #%s (SOS itself is unaffected)",
                         incident_id)


def triage_in_background(incident_id: int):
    """Run triage without making the SOS request wait. Replaced by Celery later."""
    if not getattr(settings, "SOS_TRIAGE_ASYNC", True):
        triage_incident(incident_id)
        return

    def worker():
        try:
            triage_incident(incident_id)
        finally:
            close_old_connections()

    threading.Thread(target=worker, daemon=True).start()
