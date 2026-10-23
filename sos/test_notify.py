import json
from unittest import mock

from django.test import TestCase, override_settings

from accounts.models import User
from community import services as community
from sos.services import raise_sos


@override_settings(TELEGRAM_BOT_TOKEN="t", TELEGRAM_WEBHOOK_SECRET="s3cret",
                   TELEGRAM_BOT_USERNAME="sos_bot", SITE_URL="https://sos.example")
class TelegramTests(TestCase):

    def setUp(self):
        ids = community.create_sandbox()
        self.resident = User.objects.get(id=ids["resident"])
        self.guard = User.objects.get(id=ids["security"])

    def hook(self, payload, secret="s3cret"):
        return self.client.post("/api/telegram/webhook/", json.dumps(payload),
                                content_type="application/json",
                                HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN=secret)

    @mock.patch("sos.notify._send")
    def test_start_token_links_chat(self, send):
        self.guard.telegram_link_token = "tok123"
        self.guard.save()
        self.assertEqual(self.hook({"message": {"text": "/start tok123",
                                                "chat": {"id": 777}}}).status_code, 200)
        self.guard.refresh_from_db()
        self.assertEqual(self.guard.telegram_chat_id, "777")
        self.assertEqual(self.guard.telegram_link_token, "")  # one-time token
        send.assert_called_once()

    def test_webhook_rejects_wrong_secret(self):
        self.assertEqual(self.hook({}, secret="nope").status_code, 403)

    @mock.patch("sos.notify.send_telegram")
    def test_linked_recipient_gets_telegram_alert(self, send):
        User.objects.filter(pk=self.guard.pk).update(telegram_chat_id="777")
        raise_sos(self.resident, category="fall", message="papa gir gaye",
                  latitude="20.1", longitude="85.1")
        chat_ids = [c.args[0] for c in send.call_args_list]
        self.assertEqual(chat_ids, ["777"])  # only the linked user
        text = send.call_args.args[1]
        self.assertIn("papa gir gaye", text)
        self.assertIn("maps.google.com/?q=20.1", text)
        self.assertIn("https://sos.example/board/", text)

    def test_connect_button_redirects_to_bot(self):
        self.client.force_login(self.guard)
        r = self.client.post("/circle/", {"action": "telegram_connect"})
        self.guard.refresh_from_db()
        self.assertEqual(r["Location"], f"https://t.me/sos_bot?start={self.guard.telegram_link_token}")


class MapPointTests(TestCase):

    def test_gps_wins_then_society_address(self):
        ids = community.create_sandbox()
        resident = User.objects.get(id=ids["resident"])
        self.client.force_login(resident)
        gps = raise_sos(resident, latitude="20.5", longitude="85.5")
        plain = raise_sos(resident)
        data = {i["id"]: i["map_point"] for i in self.client.get("/api/incidents/").json()}
        self.assertEqual(data[gps.id]["source"], "gps")
        self.assertEqual(data[plain.id]["source"], "society")
