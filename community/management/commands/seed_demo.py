"""python manage.py seed_demo  -> creates a demo society with one person per role.

All demo users get the password: Demo@1234
Safe to run many times (it reuses what already exists).
"""
from django.core.management.base import BaseCommand

from accounts.models import User
from community.models import EmergencyContact, Flat, GuardianLink, Residency, Society, Tower

PASSWORD = "Demo@1234"


class Command(BaseCommand):
    help = "Create demo society, flats and one user per role for testing SOS flows."

    def handle(self, *args, **options):
        society, _ = Society.objects.get_or_create(
            name="Green Valley Apartments",
            defaults={"address": "Link Road", "city": "Cuttack",
                      "latitude": 20.462500, "longitude": 85.883000},
        )
        tower, _ = Tower.objects.get_or_create(society=society, name="Block A")
        flat_402, _ = Flat.objects.get_or_create(tower=tower, number="402", defaults={"floor": 4})
        flat_101, _ = Flat.objects.get_or_create(tower=tower, number="101", defaults={"floor": 1})

        people = [
            # username,        role,                  flat,     available
            ("resident_ravi",  User.Role.RESIDENT,    flat_402, False),
            ("guardian_priya", User.Role.GUARDIAN,    None,     False),
            ("guardian_amit",  User.Role.GUARDIAN,    None,     False),
            ("volunteer_neha", User.Role.VOLUNTEER,   flat_101, True),
            ("security_raju",  User.Role.SECURITY,    None,     False),
        ]
        users = {}
        for username, role, flat, available in people:
            user, created = User.objects.get_or_create(
                username=username, defaults={"role": role, "is_available": available})
            if created:
                user.set_password(PASSWORD)
                user.save()
            users[username] = user
            # guardians live elsewhere, so they get no residency
            if role != User.Role.GUARDIAN:
                Residency.objects.update_or_create(
                    user=user, defaults={"society": society, "flat": flat})

        ravi = users["resident_ravi"]
        GuardianLink.objects.get_or_create(resident=ravi, guardian=users["guardian_priya"],
                                           defaults={"priority": 1, "relation": "Daughter"})
        GuardianLink.objects.get_or_create(resident=ravi, guardian=users["guardian_amit"],
                                           defaults={"priority": 2, "relation": "Son"})
        EmergencyContact.objects.get_or_create(
            resident=ravi, phone="9000000001",
            defaults={"name": "Dr. Mishra", "relation": "Family doctor"})

        self.stdout.write(self.style.SUCCESS(
            f"Demo data ready. Log in as any of {list(users)} with password {PASSWORD}"))
