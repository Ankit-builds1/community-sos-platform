"""Cron endpoint for hosting without Celery beat (e.g. Render free tier).

An external scheduler (cron-job.org) calls this URL every minute:
    GET /api/internal/cron/?token=<CRON_SECRET>      (or header X-Cron-Token)
It runs the same jobs Celery beat runs locally, and as a side effect keeps a
free instance from sleeping. Without CRON_SECRET set, the endpoint is disabled.
"""
import hmac

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from .services import run_due_escalations
from .tasks import cleanup_demo_data_task


@require_GET
def cron(request):
    secret = settings.CRON_SECRET
    given = request.headers.get("X-Cron-Token") or request.GET.get("token", "")
    if not secret or not hmac.compare_digest(given, secret):  # constant-time compare
        return JsonResponse({"detail": "forbidden"}, status=403)
    return JsonResponse({
        "escalated": run_due_escalations(),
        "demo_incidents_deleted": cleanup_demo_data_task(),
    })


def healthz(request):
    """Tiny health check for the hosting platform (no auth, no database)."""
    return JsonResponse({"status": "ok"})
