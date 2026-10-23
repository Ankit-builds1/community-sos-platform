"""Tests for production hardening: LLM budget, demo mode, rate limits, demo clean-up."""
from datetime import timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.models import User
from sos.models import Incident
from sos.tasks import cleanup_demo_data_task

from .llm_budget import LLMBudgetExceeded, calls_used_today, spend_llm_call


class LLMBudgetTests(TestCase):

    def setUp(self):
        cache.clear()

    @override_settings(LLM_DAILY_CALL_LIMIT=2)
    def test_budget_blocks_after_limit(self):
        spend_llm_call("a")
        spend_llm_call("b")
        with self.assertRaises(LLMBudgetExceeded):
            spend_llm_call("c")
        self.assertEqual(calls_used_today(), 3)

    @override_settings(LLM_DAILY_CALL_LIMIT=0, GROQ_API_KEY="test")
    @patch("triage.llm.Groq")
    def test_triage_falls_back_to_rules_when_budget_is_used_up(self, groq_cls):
        from triage.graph import run_triage
        with override_settings(LLM_DAILY_CALL_LIMIT=1):
            spend_llm_call("used up")
            final = run_triage("chest pain", "other")["final"]
        self.assertEqual(final.source, "rules")
        self.assertEqual(final.severity, "critical")
        groq_cls.assert_not_called()  # no tokens spent


class DemoModeTests(APITestCase):

    def setUp(self):
        cache.clear()
        self.resident = User.objects.create_user("ravi", password="pass12345!")

    @override_settings(DEMO_MODE=True)
    def test_signup_is_disabled_in_demo_mode(self):
        response = self.client.post("/api/auth/register/", {
            "username": "new", "password": "Very-strong-pass-123", "role": "resident"},
            format="json")
        self.assertEqual(response.status_code, 403)

    @override_settings(DEMO_MODE=False)
    def test_signup_works_outside_demo_mode(self):
        response = self.client.post("/api/auth/register/", {
            "username": "new", "password": "Very-strong-pass-123", "role": "resident"},
            format="json")
        self.assertEqual(response.status_code, 201)

    @override_settings(DEMO_MODE=False)
    def test_real_sos_is_never_rate_limited(self):
        self.client.force_authenticate(self.resident)
        with patch("config.throttles.SOSRaiseThrottle.get_rate", return_value="1/hour"):
            codes = [self.client.post("/api/incidents/raise/", {}, format="json").status_code
                     for _ in range(3)]
        self.assertEqual(codes, [201, 201, 201])

    @override_settings(DEMO_MODE=True)
    def test_demo_sos_is_rate_limited(self):
        self.client.force_authenticate(self.resident)
        with patch("config.throttles.SOSRaiseThrottle.get_rate", return_value="2/hour"):
            codes = [self.client.post("/api/incidents/raise/", {}, format="json").status_code
                     for _ in range(3)]
        self.assertEqual(codes, [201, 201, 429])

    @override_settings(DEMO_MODE=True, DEMO_RETENTION_HOURS=24)
    def test_demo_cleanup_deletes_only_old_incidents(self):
        old = Incident.objects.create(resident=self.resident, message="old")
        Incident.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(hours=30))
        fresh = Incident.objects.create(resident=self.resident, message="fresh")
        cleanup_demo_data_task()
        self.assertFalse(Incident.objects.filter(pk=old.pk).exists())
        self.assertTrue(Incident.objects.filter(pk=fresh.pk).exists())
