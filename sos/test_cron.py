from django.test import TestCase, override_settings


class CronEndpointTests(TestCase):

    @override_settings(CRON_SECRET="")
    def test_disabled_without_secret(self):
        self.assertEqual(self.client.get("/api/internal/cron/?token=").status_code, 403)

    @override_settings(CRON_SECRET="s3cret")
    def test_wrong_token_is_rejected(self):
        self.assertEqual(self.client.get("/api/internal/cron/?token=nope").status_code, 403)

    @override_settings(CRON_SECRET="s3cret")
    def test_correct_token_runs_jobs(self):
        response = self.client.get("/api/internal/cron/", HTTP_X_CRON_TOKEN="s3cret")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"escalated": 0, "demo_incidents_deleted": 0})

    def test_healthz(self):
        self.assertEqual(self.client.get("/healthz").json(), {"status": "ok"})
