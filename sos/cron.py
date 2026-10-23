"""Cron endpoint for hosting without Celery beat (e.g. Render free tier).

An external scheduler (cron-job.org) calls this URL every minute:
    GET /api/internal/cron/?token=<CRON_SECRET>      (or header X-Cron-Token)
It runs the same jobs Celery beat runs locally, and as a side effect keeps a
free instance from sleeping. Without CRON_SECRET set, the endpoint is disabled.
"""
import hmac
import json

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .notify import handle_update
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


@csrf_exempt
@require_POST
def telegram_webhook(request):
    """Telegram calls this for every bot message. Verified by the secret header that
    Telegram sends back (set with `manage.py telegram_webhook`)."""
    secret = settings.TELEGRAM_WEBHOOK_SECRET
    given = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not secret or not hmac.compare_digest(given, secret):
        return JsonResponse({"detail": "forbidden"}, status=403)
    try:
        handle_update(json.loads(request.body or b"{}"))
    except ValueError:
        pass
    return JsonResponse({"ok": True})  # always 200, or Telegram keeps retrying


def healthz(request):
    """Tiny health check for the hosting platform (no auth, no database)."""
    return JsonResponse({"status": "ok"})
