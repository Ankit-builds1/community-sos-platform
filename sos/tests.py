"""Tests for the full SOS flow: raise -> alert -> escalate -> accept -> resolve.

Run with:  python manage.py test
"""
from datetime import timedelta

from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User
from community.models import EmergencyContact, Flat, GuardianLink, Residency, Society, Tower

from .models import Alert, Incident
from .services import MAX_LEVEL, run_due_escalations


class SOSFlowTests(APITestCase):

    @classmethod
    def setUpTestData(cls):
        society = Society.objects.create(name="Test Society", address="x", city="Cuttack")
        tower = Tower.objects.create(society=society, name="A")
        flat = Flat.objects.create(tower=tower, number="101", floor=1)

        def make(username, role, **extra):
            user = User.objects.create_user(username=username, password="pass12345!",
                                            role=role, **extra)
            return user

        cls.resident = make("ravi", User.Role.RESIDENT)
        cls.primary = make("priya", User.Role.GUARDIAN)
        cls.secondary = make("amit", User.Role.GUARDIAN)
        cls.volunteer = make("neha", User.Role.VOLUNTEER, is_available=True)
        cls.busy_volunteer = make("sam", User.Role.VOLUNTEER, is_available=False)
        cls.guard = make("raju", User.Role.SECURITY)
        cls.stranger = make("stranger", User.Role.RESIDENT)

        Residency.objects.create(user=cls.resident, society=society, flat=flat)
        for user in (cls.volunteer, cls.busy_volunteer, cls.guard):
            Residency.objects.create(user=user, society=society)

        GuardianLink.objects.create(resident=cls.resident, guardian=cls.primary, priority=1)
        GuardianLink.objects.create(resident=cls.resident, guardian=cls.secondary, priority=2)
        EmergencyContact.objects.create(resident=cls.resident, name="Doc", phone="9000000001")

    # ---------- helpers ----------

    def raise_sos(self, **payload):
        self.client.force_authenticate(self.resident)
        payload.setdefault("category", "fall")
        return self.client.post("/api/incidents/raise/", payload, format="json")

    def expire_current_level(self, incident):
        """Pretend the escalation timeout has passed for this incident."""
        Incident.objects.filter(pk=incident.pk).update(
            last_escalated_at=timezone.now() - timedelta(hours=1))

    def recipients(self, incident, level):
        return set(Alert.objects.filter(incident=incident, escalation_level=level)
                   .values_list("recipient__username", flat=True))

    # ---------- raising an SOS ----------

    def test_login_required(self):
        response = self.client.post("/api/incidents/raise/", {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_one_tap_sos_with_empty_body_works(self):
        self.client.force_authenticate(self.resident)
        response = self.client.post("/api/incidents/raise/", {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_raise_alerts_primary_guardian_security_and_available_volunteers(self):
        response = self.raise_sos(message="Slipped in bathroom")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        incident = Incident.objects.get(pk=response.data["id"])

        self.assertEqual(incident.status, Incident.Status.OPEN)
        self.assertEqual(incident.flat.number, "101")
        # secondary guardian and the busy volunteer must NOT be alerted at level 1
        self.assertEqual(self.recipients(incident, 1), {"priya", "raju", "neha"})
        self.assertTrue(all(a.status == Alert.Status.SENT for a in incident.alerts.all()))

    # ---------- escalation ----------

    def test_nothing_escalates_before_timeout(self):
        self.raise_sos()
        self.assertEqual(run_due_escalations(), 0)

    def test_escalation_walks_all_levels_then_flags_human_review(self):
        incident = Incident.objects.get(pk=self.raise_sos().data["id"])

        self.expire_current_level(incident)
        run_due_escalations()
        incident.refresh_from_db()
        self.assertEqual(incident.escalation_level, 2)
        self.assertEqual(incident.status, Incident.Status.ESCALATED)
        self.assertEqual(self.recipients(incident, 2), {"amit"})

        self.expire_current_level(incident)
        run_due_escalations()
        incident.refresh_from_db()
        self.assertEqual(incident.escalation_level, MAX_LEVEL)
        sms = Alert.objects.get(incident=incident, escalation_level=3)
        self.assertEqual((sms.channel, sms.recipient_phone), ("sms", "9000000001"))

        self.expire_current_level(incident)
        run_due_escalations()
        incident.refresh_from_db()
        self.assertTrue(incident.needs_human_review)
        self.assertEqual(incident.escalation_level, MAX_LEVEL)  # never goes past the max

    # ---------- responder actions ----------

    def test_accept_makes_incident_active_and_stops_escalation(self):
        incident_id = self.raise_sos().data["id"]
        self.client.force_authenticate(self.volunteer)
        response = self.client.post(f"/api/incidents/{incident_id}/accept/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "active")
        self.assertEqual(response.data["assigned_responder"], self.volunteer.pk)

        incident = Incident.objects.get(pk=incident_id)
        self.expire_current_level(incident)
        self.assertEqual(run_due_escalations(), 0)

    def test_first_responder_wins(self):
        incident_id = self.raise_sos().data["id"]
        self.client.force_authenticate(self.volunteer)
        self.client.post(f"/api/incidents/{incident_id}/accept/")
        self.client.force_authenticate(self.guard)
        response = self.client.post(f"/api/incidents/{incident_id}/accept/")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Incident.objects.get(pk=incident_id).assigned_responder, self.volunteer)

    def test_stranger_cannot_see_or_accept_incident(self):
        incident_id = self.raise_sos().data["id"]
        self.client.force_authenticate(self.stranger)
        response = self.client.post(f"/api/incidents/{incident_id}/accept/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_decline_records_response_without_changing_status(self):
        incident_id = self.raise_sos().data["id"]
        self.client.force_authenticate(self.volunteer)
        self.client.post(f"/api/incidents/{incident_id}/decline/")
        alert = Alert.objects.get(incident_id=incident_id, recipient=self.volunteer)
        self.assertEqual(alert.status, Alert.Status.DECLINED)
        self.assertEqual(Incident.objects.get(pk=incident_id).status, Incident.Status.OPEN)

    def test_assigned_responder_can_resolve(self):
        incident_id = self.raise_sos().data["id"]
        self.client.force_authenticate(self.volunteer)
        self.client.post(f"/api/incidents/{incident_id}/accept/")
        response = self.client.post(f"/api/incidents/{incident_id}/resolve/")
        self.assertEqual(response.data["status"], "resolved")
        self.assertIsNotNone(response.data["resolved_at"])

    def test_unrelated_alerted_user_cannot_resolve(self):
        incident_id = self.raise_sos().data["id"]
        self.client.force_authenticate(self.volunteer)
        self.client.post(f"/api/incidents/{incident_id}/accept/")
        self.client.force_authenticate(self.primary)  # alerted, but not the responder
        response = self.client.post(f"/api/incidents/{incident_id}/resolve/")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
