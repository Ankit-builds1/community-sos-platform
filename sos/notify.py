"""Real notifications through a free Telegram bot.

Setup (once): create a bot with @BotFather, then set TELEGRAM_BOT_TOKEN,
TELEGRAM_BOT_USERNAME and TELEGRAM_WEBHOOK_SECRET, and run
    python manage.py telegram_webhook https://<your-site>
Users link their account from "My circle" -> "Connect Telegram".
Without a token everything here is a silent no-op (local dev, tests).
"""
import json
import logging
import threading
import urllib.request

from django.conf import settings
from django.db import transaction

logger = logging.getLogger(__name__)
SEV_ICON = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}


def enabled():
    return bool(settings.TELEGRAM_BOT_TOKEN)


def telegram_api(method, payload, timeout=8):
    url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/{method}"
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as res:
        return json.loads(res.read())


def _send(chat_id, text):
    try:
        telegram_api("sendMessage", {"chat_id": chat_id, "text": text,
                                     "disable_web_page_preview": True})
    except Exception as exc:  # a notification failure must never break an SOS
        logger.warning("Telegram send to %s failed: %s", chat_id, exc)


def send_telegram(chat_id, text):
    """Send after the DB commit, in a background thread, so the SOS request never waits."""
    if not (enabled() and chat_id):
        return
    transaction.on_commit(
        lambda: threading.Thread(target=_send, args=(chat_id, text), daemon=True).start())


def alert_text(alert):
    i = alert.incident
    where = f"{i.flat.tower.name} · Flat {i.flat.number}" if i.flat_id else "their location"
    sev = f"{SEV_ICON.get(i.severity, '')} {i.severity.upper()}\n" if i.severity else ""
    lines = [f"🚨 SOS #{i.pk} from {i.resident.first_name or i.resident.username} ({where})",
             sev + f"Category: {i.category}"]
    if i.message:
        lines.append(f"“{i.message[:300]}”")
    if i.latitude is not None and i.longitude is not None:
        lines.append(f"📍 https://maps.google.com/?q={i.latitude},{i.longitude}")
    lines.append(f"You were alerted as: {alert.get_audience_display()} (level {alert.escalation_level})")
    if settings.SITE_URL:
        lines.append(f"Respond: {settings.SITE_URL}/board/")
    return "\n".join(lines)


def handle_update(update):
    """Webhook: '/start <token>' links a Telegram chat to a user account."""
    from accounts.models import User

    msg = update.get("message") or {}
    text, chat = msg.get("text", ""), (msg.get("chat") or {}).get("id")
    if not chat or not text.startswith("/start"):
        return
    token = text.partition(" ")[2].strip()
    user = User.objects.filter(telegram_link_token=token).first() if token else None
    if user:
        user.telegram_chat_id, user.telegram_link_token = str(chat), ""
        user.save(update_fields=["telegram_chat_id", "telegram_link_token"])
        _send(chat, f"✅ Linked to {user.username}. You'll get SOS alerts here.")
    else:
        _send(chat, "Open “My circle” on Community SOS and press “Connect Telegram” to link.")
