"""python manage.py run_escalations   -> checks every 10 s and escalates unanswered SOS.

Simple worker for development. Will be replaced by a Celery beat task later.
"""
import time

from django.core.management.base import BaseCommand

from sos.services import escalation_timeout, run_due_escalations


class Command(BaseCommand):
    help = "Keep escalating unanswered incidents whose timeout has passed."

    def add_arguments(self, parser):
        parser.add_argument("--interval", type=int, default=10, help="seconds between checks")
        parser.add_argument("--once", action="store_true", help="check one time and exit")

    def handle(self, *args, interval, once, **options):
        self.stdout.write(self.style.SUCCESS(
            f"Escalation worker started (timeout {escalation_timeout()}, every {interval}s). "
            "Ctrl+C to stop."))
        while True:
            count = run_due_escalations()
            if count:
                self.stdout.write(self.style.WARNING(f"Escalated {count} incident(s)"))
            if once:
                break
            time.sleep(interval)
