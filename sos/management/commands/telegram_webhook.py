from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from sos.notify import telegram_api


class Command(BaseCommand):
    help = "Point the Telegram bot at this site: manage.py telegram_webhook https://your-site"

    def add_arguments(self, parser):
        parser.add_argument("site_url", nargs="?", default=settings.SITE_URL)

    def handle(self, site_url, **opts):
        if not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_WEBHOOK_SECRET:
            raise CommandError("Set TELEGRAM_BOT_TOKEN and TELEGRAM_WEBHOOK_SECRET first.")
        if not site_url:
            raise CommandError("Pass the public https URL of the site.")
        url = site_url.rstrip("/") + "/api/telegram/webhook/"
        res = telegram_api("setWebhook", {"url": url, "allowed_updates": ["message"],
                                          "secret_token": settings.TELEGRAM_WEBHOOK_SECRET})
        self.stdout.write(self.style.SUCCESS(f"Webhook -> {url}: {res.get('description')}"))
