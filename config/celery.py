"""Celery app: background tasks (AI triage) and scheduled tasks (escalation checks).

Run (Windows needs --pool=solo):
    celery -A config worker --pool=solo -l info
    celery -A config beat -l info
"""
import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("config")
app.config_from_object("django.conf:settings", namespace="CELERY")  # reads CELERY_* settings
app.autodiscover_tasks()  # finds tasks.py in every installed app
