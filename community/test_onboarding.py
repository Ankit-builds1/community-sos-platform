from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone

from accounts.models import User
from community import services
from community.models import Flat, GuardianLink, JoinRequest, Residency, Society


class OnboardingTests(TestCase):

    def make(self, name, role=User.Role.RESIDENT):
        return User.objects.create_user(name, password="pass12345!", role=role)

    @override_settings(DEMO_MODE=True)
    def test_register_society_in_demo_is_live_sandbox(self):
        owner = self.make("owner")
        s = services.register_society(owner, "Lotus Towers", "Rd 1", "Puri", 2, 3, 2)
        owner.refresh_from_db()
        self.assertEqual(s.status, Society.Status.APPROVED)
        self.assertTrue(s.is_sandbox and s.expires_at)
        self.assertEqual(Flat.objects.filter(tower__society=s).count(), 2 * 3 * 2)
        self.assertEqual(owner.role, User.Role.MANAGER)
        self.assertEqual(len(s.join_code), 6)

    @override_settings(DEMO_MODE=False)
    def test_register_society_in_real_mode_waits_for_admin(self):
        s = services.register_society(self.make("owner"), "Real", "x", "y")
        self.assertEqual(s.status, Society.Status.PENDING)
        with self.assertRaises(services.OnboardingError):  # code not usable yet
            services.request_join(self.make("joe"), s.join_code, None, "volunteer")

    @override_settings(DEMO_MODE=True)
    def test_join_and_manager_approval(self):
        manager = self.make("mgr")
        s = services.register_society(manager, "Lotus", "x", "y")
        flat = Flat.objects.filter(tower__society=s).first()
        joe = self.make("joe")
        jr = services.request_join(joe, s.join_code.lower(), flat.id, "resident")
        # another manager cannot approve it
        other = self.make("other")
        services.register_society(other, "Other", "x", "y")
        with self.assertRaises(services.OnboardingError):
            services.decide_join(other, jr.id, True)
        services.decide_join(manager, jr.id, True)
        self.assertEqual(Residency.objects.get(user=joe).flat, flat)

    @override_settings(DEMO_MODE=True)
    def test_resident_must_pick_flat(self):
        s = services.register_society(self.make("mgr"), "Lotus", "x", "y")
        with self.assertRaises(services.OnboardingError):
            services.request_join(self.make("joe"), s.join_code, None, "resident")

    def test_guardian_invite(self):
        ravi, mum = self.make("ravi"), self.make("mum")
        inv = services.create_invite(ravi, 1, "Mother")
        with self.assertRaises(services.OnboardingError):
            services.accept_invite(ravi, inv.token)  # not your own guardian
        services.accept_invite(mum, inv.token)
        self.assertTrue(GuardianLink.objects.filter(resident=ravi, guardian=mum).exists())
        with self.assertRaises(services.OnboardingError):
            services.accept_invite(self.make("x"), inv.token)  # single use

    def test_sandbox_and_cleanup(self):
        ids = services.create_sandbox()
        self.assertEqual(len(ids), 6)
        User.objects.filter(id__in=ids.values()).update(expires_at=timezone.now() - timedelta(1))
        Society.objects.filter(is_sandbox=True).update(expires_at=timezone.now() - timedelta(1))
        services.cleanup_expired_sandboxes()
        self.assertFalse(User.objects.filter(id__in=ids.values()).exists())
        self.assertFalse(Society.objects.filter(is_sandbox=True).exists())


class SandboxWebTests(TestCase):

    def test_sandbox_flow_and_role_switch(self):
        r = self.client.post("/sandbox/")
        self.assertRedirects(r, "/board/")
        users = self.client.session["sandbox_users"]
        self.client.post("/sandbox/as/security/")
        self.assertEqual(int(self.client.session["_auth_user_id"]), users["security"])
        # resident raises an SOS, the sandbox guard sees it
        self.client.post("/sandbox/as/resident/")
        res = self.client.post("/api/incidents/raise/", {"message": "test fall"},
                               content_type="application/json")
        self.assertEqual(res.status_code, 201)
        self.client.post("/sandbox/as/security/")
        self.assertEqual(len(self.client.get("/api/incidents/").json()), 1)

    def test_cannot_switch_into_someone_elses_sandbox(self):
        other = services.create_sandbox()
        self.client.post("/sandbox/")
        self.client.post("/sandbox/as/manager/")
        self.assertNotEqual(int(self.client.session["_auth_user_id"]), other["manager"])
        self.assertEqual(self.client.post("/sandbox/as/nobody/").status_code, 403)

    def test_manager_page_and_approve(self):
        self.client.post("/sandbox/")
        self.client.post("/sandbox/as/manager/")
        self.assertContains(self.client.get("/manage/"), "Join code")
