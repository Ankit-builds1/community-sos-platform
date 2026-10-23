"""Self-service onboarding: register a society, join with a code, guardian invites, sandbox."""
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from accounts.models import User
from .models import (EmergencyContact, Flat, GuardianInvite, GuardianLink, JoinRequest,
                     Residency, Society, Tower)

SANDBOX_HOURS = 24
MAX_TOWERS, MAX_FLOORS, MAX_FLATS_PER_FLOOR = 10, 40, 12


class OnboardingError(Exception):
    pass


def sandbox_expiry():
    return timezone.now() + timedelta(hours=SANDBOX_HOURS)


def _build_flats(society, tower_names, floors, flats_per_floor):
    for tname in tower_names:
        tower = Tower.objects.create(society=society, name=tname)
        Flat.objects.bulk_create([
            Flat(tower=tower, number=f"{f}{n:02d}", floor=f)
            for f in range(1, floors + 1) for n in range(1, flats_per_floor + 1)
        ])


def _coord(value, limit):
    try:
        v = round(float(value), 6)
    except (TypeError, ValueError):
        return None
    return v if -limit <= v <= limit else None


@transaction.atomic
def register_society(user, name, address, city, towers=1, floors=4, flats_per_floor=4,
                     sandbox=None, latitude=None, longitude=None):
    """Creator becomes the Society Manager. Demo mode: approved instantly but expires."""
    if hasattr(user, "residency"):
        raise OnboardingError("You already belong to a society.")
    towers = max(1, min(int(towers), MAX_TOWERS))
    floors = max(1, min(int(floors), MAX_FLOORS))
    flats_per_floor = max(1, min(int(flats_per_floor), MAX_FLATS_PER_FLOOR))
    if sandbox is None:
        sandbox = settings.DEMO_MODE

    society = Society.objects.create(
        name=name.strip()[:150], address=address.strip() or "-", city=city.strip()[:80] or "-",
        created_by=user, is_sandbox=sandbox,
        latitude=_coord(latitude, 90), longitude=_coord(longitude, 180),
        expires_at=sandbox_expiry() if sandbox else None,
        status=Society.Status.APPROVED if sandbox else Society.Status.PENDING,
    )
    names = [f"Block {chr(65 + i)}" for i in range(towers)]
    _build_flats(society, names, floors, flats_per_floor)
    society.ensure_join_code()

    user.role = User.Role.MANAGER
    user.save(update_fields=["role"])
    Residency.objects.create(user=user, society=society)
    return society


def request_join(user, code, flat_id=None, role="resident", note=""):
    if hasattr(user, "residency"):
        raise OnboardingError("You already belong to a society.")
    society = Society.objects.filter(join_code=(code or "").strip().upper(),
                                     status=Society.Status.APPROVED).first()
    if not society:
        raise OnboardingError("Invalid or inactive join code.")
    if role not in dict(JoinRequest.ROLE_CHOICES):
        raise OnboardingError("Invalid role.")
    flat = None
    if flat_id:
        flat = Flat.objects.filter(id=flat_id, tower__society=society).first()
        if not flat:
            raise OnboardingError("That flat is not in this society.")
    if role == "resident" and not flat:
        raise OnboardingError("Residents must pick their flat.")
    JoinRequest.objects.filter(user=user, status=JoinRequest.Status.PENDING).delete()
    return JoinRequest.objects.create(user=user, society=society, flat=flat, role=role,
                                      note=note[:200])


def managed_society(user):
    """The society this user manages, or None."""
    if user.role != User.Role.MANAGER or not hasattr(user, "residency"):
        return None
    return user.residency.society


@transaction.atomic
def decide_join(manager, request_id, approve):
    society = managed_society(manager)
    jr = JoinRequest.objects.select_for_update().filter(
        id=request_id, society=society, status=JoinRequest.Status.PENDING).first()
    if not society or not jr:
        raise OnboardingError("Request not found.")
    jr.status = JoinRequest.Status.APPROVED if approve else JoinRequest.Status.REJECTED
    jr.decided_by, jr.decided_at = manager, timezone.now()
    jr.save()
    if approve:
        Residency.objects.update_or_create(user=jr.user,
                                           defaults={"society": society, "flat": jr.flat})
        jr.user.role = jr.role
        jr.user.save(update_fields=["role"])
    return jr


def create_invite(resident, priority=1, relation=""):
    return GuardianInvite.objects.create(resident=resident, priority=max(1, int(priority)),
                                         relation=relation[:50])


@transaction.atomic
def accept_invite(user, token):
    inv = GuardianInvite.objects.select_for_update().filter(
        token=token, accepted_by__isnull=True).first()
    if not inv:
        raise OnboardingError("This invite is invalid or already used.")
    if inv.resident_id == user.id:
        raise OnboardingError("You cannot be your own guardian.")
    GuardianLink.objects.update_or_create(
        resident=inv.resident, guardian=user,
        defaults={"priority": inv.priority, "relation": inv.relation})
    if user.role == User.Role.RESIDENT and not hasattr(user, "residency"):
        user.role = User.Role.GUARDIAN
        user.save(update_fields=["role"])
    inv.accepted_by, inv.accepted_at = user, timezone.now()
    inv.save()
    return inv


SANDBOX_ROLES = [
    ("resident", "Resident", User.Role.RESIDENT),
    ("guardian1", "Guardian (P1)", User.Role.GUARDIAN),
    ("guardian2", "Guardian (P2)", User.Role.GUARDIAN),
    ("volunteer", "Volunteer", User.Role.VOLUNTEER),
    ("security", "Security", User.Role.SECURITY),
    ("manager", "Society Manager", User.Role.MANAGER),
]


@transaction.atomic
def create_sandbox():
    """A private throw-away society for one visitor. Returns {role_key: user_id}."""
    tag = secrets.token_hex(3).upper()
    exp = sandbox_expiry()
    society = Society.objects.create(name=f"Sandbox Heights {tag}", address="Demo Road",
                                     city="Bhubaneswar", is_sandbox=True, expires_at=exp,
                                     latitude=20.296100, longitude=85.824500)
    _build_flats(society, ["Block A", "Block B"], 4, 4)
    society.ensure_join_code()
    flat = Flat.objects.get(tower__society=society, tower__name="Block A", number="402")

    users = {}
    for key, label, role in SANDBOX_ROLES:
        u = User(username=f"sb_{tag.lower()}_{key}", role=role, first_name=label,
                 is_sandbox=True, expires_at=exp, is_available=True)
        u.set_unusable_password()
        u.save()
        users[key] = u
        if key in ("resident", "volunteer", "security", "manager"):
            Residency.objects.create(user=u, society=society,
                                     flat=flat if key == "resident" else None)
    society.created_by = users["manager"]
    society.save(update_fields=["created_by"])
    GuardianLink.objects.create(resident=users["resident"], guardian=users["guardian1"],
                                priority=1, relation="Daughter")
    GuardianLink.objects.create(resident=users["resident"], guardian=users["guardian2"],
                                priority=2, relation="Son")
    EmergencyContact.objects.create(resident=users["resident"], name="Dr. Demo",
                                    phone="9000000001", relation="Family doctor")
    return {k: u.id for k, u in users.items()}


def cleanup_expired_sandboxes():
    """Delete expired sandbox societies and users. Returns (societies, users) deleted."""
    now = timezone.now()
    s, _ = Society.objects.filter(is_sandbox=True, expires_at__lt=now).delete()
    u, _ = User.objects.filter(is_sandbox=True, expires_at__lt=now).delete()
    return s, u
