from django.test import TestCase

from accounts.models import User
from community.models import Flat, Residency, Society, Tower
from sos.models import Incident


class DashboardTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        society = Society.objects.create(name="S", address="x", city="Cuttack")
        flat = Flat.objects.create(tower=Tower.objects.create(society=society, name="Block A"),
                                   number="402")
        cls.resident = User.objects.create_user("ravi", password="pass12345!",
                                                role=User.Role.RESIDENT)
        cls.guard = User.objects.create_user("raju", password="pass12345!",
                                             role=User.Role.SECURITY)
        cls.stranger = User.objects.create_user("x", password="pass12345!",
                                                role=User.Role.RESIDENT)
        Residency.objects.create(user=cls.resident, society=society, flat=flat)
        Residency.objects.create(user=cls.guard, society=society)
        # created directly (no alerts), so only the society rule can make it visible
        cls.incident = Incident.objects.create(resident=cls.resident, society=society,
                                               flat=flat, message="help")

    def test_board_requires_login(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response["Location"])

    def test_login_page_lists_demo_accounts(self):
        response = self.client.get("/login/")
        self.assertContains(response, "security_raju")

    def test_board_renders_for_logged_in_user(self):
        self.client.force_login(self.resident)
        response = self.client.get("/")
        self.assertContains(response, "Incident board")
        self.assertContains(response, "Send SOS")  # residents get the SOS form

    def test_guard_sees_every_incident_in_their_society(self):
        self.client.force_login(self.guard)
        ids = [i["id"] for i in self.client.get("/api/incidents/").json()]
        self.assertIn(self.incident.id, ids)

    def test_unrelated_user_does_not_see_it(self):
        self.client.force_login(self.stranger)
        self.assertEqual(self.client.get("/api/incidents/").json(), [])

    def test_api_includes_location_for_display(self):
        self.client.force_login(self.resident)
        incident = self.client.get(f"/api/incidents/{self.incident.id}/").json()
        self.assertEqual(incident["location"], "Block A · Flat 402")
