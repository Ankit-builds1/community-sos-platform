import secrets

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST

from accounts.models import User
from community import services
from community.models import (EmergencyContact, Flat, GuardianInvite, GuardianLink,
                              JoinRequest, Society)

BACKEND = "django.contrib.auth.backends.ModelBackend"
DEMO_ACCOUNTS = [
    ("security_raju", "Security guard: sees every SOS in the society"),
    ("resident_ravi", "Resident: raises an SOS"),
    ("guardian_priya", "Primary guardian: alerted first"),
    ("volunteer_neha", "Volunteer: can accept and help"),
]


def _client_ip(request):
    fwd = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return fwd.split(",")[0].strip() or request.META.get("REMOTE_ADDR", "?")


def _rate_ok(request, bucket, limit, seconds=3600):
    """Small per-IP limiter for anonymous web actions (sandbox, sign-up)."""
    key = f"rl:{bucket}:{_client_ip(request)}"
    cache.add(key, 0, seconds)
    try:
        n = cache.incr(key)
    except ValueError:
        cache.set(key, 1, seconds)
        n = 1
    return n <= limit


def _safe_next(request, fallback):
    nxt = request.POST.get("next") or request.GET.get("next") or ""
    if nxt and url_has_allowed_host_and_scheme(nxt, {request.get_host()},
                                               require_https=request.is_secure()):
        return nxt
    return fallback


def landing(request):
    if request.user.is_authenticated:
        return redirect("board")
    return render(request, "dashboard/landing.html", {"demo_mode": settings.DEMO_MODE})


@login_required
@ensure_csrf_cookie  # the board's JavaScript needs the CSRF cookie for POST requests
def board(request):
    """Live incident board. Data comes from the REST API (session auth), polled every 5 s."""
    user = request.user
    has_res = hasattr(user, "residency")
    return render(request, "dashboard/board.html", {
        "can_raise": user.role == User.Role.RESIDENT and has_res,
        "no_society": not has_res and not user.is_staff
                      and not GuardianLink.objects.filter(guardian=user).exists(),
        "pending_join": JoinRequest.objects.filter(user=user,
                                                   status=JoinRequest.Status.PENDING).first(),
    })


# ---------- Instant sandbox ----------

@require_POST
def sandbox_start(request):
    if not _rate_ok(request, "sandbox", 10):
        messages.error(request, "Too many sandboxes from your network. Try again in an hour.")
        return redirect("landing")
    users = services.create_sandbox()
    login(request, User.objects.get(id=users["resident"]), backend=BACKEND)
    request.session["sandbox_users"] = users
    messages.success(request, "Your private sandbox is ready. You are the resident: send an "
                              "SOS, then switch roles from the bar above to respond.")
    return redirect("board")


@require_POST
def sandbox_switch(request, role):
    users = request.session.get("sandbox_users") or {}
    uid = users.get(role)
    if not uid:
        return HttpResponseForbidden("Not part of your sandbox.")
    user = get_object_or_404(User, id=uid, is_sandbox=True)
    login(request, user, backend=BACKEND)
    request.session["sandbox_users"] = users
    return redirect(_safe_next(request, "board"))


# ---------- Sign up / register society / join ----------

def signup(request):
    if request.user.is_authenticated:
        return redirect("board")
    error = None
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        if not _rate_ok(request, "signup", 10):
            error = "Too many sign-ups from your network. Try again later."
        elif not username or len(password) < 8:
            error = "Pick a username and a password of at least 8 characters."
        elif User.objects.filter(username__iexact=username).exists():
            error = "That username is taken."
        else:
            user = User(username=username[:150], first_name=request.POST.get("name", "")[:150])
            user.set_password(password)
            if settings.DEMO_MODE:  # public demo: every new account is temporary
                user.is_sandbox, user.expires_at = True, services.sandbox_expiry()
            user.save()
            login(request, user, backend=BACKEND)
            return redirect(_safe_next(request, "onboard"))
    return render(request, "dashboard/signup.html",
                  {"error": error, "next": request.GET.get("next", ""),
                   "demo_mode": settings.DEMO_MODE})


@login_required
def onboard(request):
    return render(request, "dashboard/onboard.html")


@login_required
def register_society(request):
    error = None
    if request.method == "POST":
        p = request.POST
        if not p.get("name", "").strip():
            error = "Society name is required."
        else:
            try:
                society = services.register_society(
                    request.user, p["name"], p.get("address", ""), p.get("city", ""),
                    p.get("towers") or 1, p.get("floors") or 4, p.get("flats") or 4,
                    latitude=p.get("latitude"), longitude=p.get("longitude"))
            except (services.OnboardingError, ValueError) as exc:
                error = str(exc)
            else:
                if society.status == Society.Status.PENDING:
                    messages.info(request, "Society submitted. An admin will approve it soon.")
                else:
                    messages.success(request, f"{society.name} is live! Share the join code "
                                              f"{society.join_code} with residents.")
                return redirect("manage")
    return render(request, "dashboard/register_society.html", {"error": error})


@login_required
def join(request, code=""):
    code = (request.POST.get("code") or request.GET.get("code") or code).strip().upper()
    society = (Society.objects.filter(join_code=code, status=Society.Status.APPROVED).first()
               if code else None)
    error = "No active society has that code." if code and not society else None
    if request.method == "POST" and society and "role" in request.POST:
        try:
            services.request_join(request.user, code, request.POST.get("flat") or None,
                                  request.POST.get("role", "resident"),
                                  request.POST.get("note", ""))
        except services.OnboardingError as exc:
            error = str(exc)
        else:
            messages.success(request, f"Request sent to the manager of {society.name}.")
            return redirect("board")
    flats = (Flat.objects.filter(tower__society=society).select_related("tower")
             .order_by("tower__name", "floor", "number")) if society else []
    return render(request, "dashboard/join.html",
                  {"code": code, "society": society, "flats": flats, "error": error,
                   "roles": JoinRequest.ROLE_CHOICES})


# ---------- Society manager ----------

@login_required
def manage(request):
    society = services.managed_society(request.user)
    if not society:
        messages.error(request, "Only a society manager can open that page.")
        return redirect("board")
    return render(request, "dashboard/manage.html", {
        "society": society,
        "join_url": request.build_absolute_uri(f"/join/{society.join_code}/"),
        "pending": society.join_requests.filter(status=JoinRequest.Status.PENDING)
                          .select_related("user", "flat__tower"),
        "members": society.members.select_related("user", "flat__tower")
                          .order_by("user__role", "user__username"),
        "flat_count": Flat.objects.filter(tower__society=society).count(),
    })


@login_required
@require_POST
def decide(request, pk, verdict):
    try:
        jr = services.decide_join(request.user, pk, verdict == "approve")
        messages.success(request, f"{jr.user.username}: {jr.status}.")
    except services.OnboardingError as exc:
        messages.error(request, str(exc))
    return redirect("manage")


# ---------- My circle (guardians + contacts) ----------

@login_required
def circle(request):
    user = request.user
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "invite":
            try:
                services.create_invite(user, request.POST.get("priority") or 1,
                                       request.POST.get("relation", ""))
                messages.success(request, "Invite link created. Send it to your guardian.")
            except ValueError:
                messages.error(request, "Priority must be a number.")
        elif action == "contact" and request.POST.get("name") and request.POST.get("phone"):
            EmergencyContact.objects.create(resident=user, name=request.POST["name"][:100],
                                            phone=request.POST["phone"][:15],
                                            relation=request.POST.get("relation", "")[:50])
        elif action == "remove_guardian":
            GuardianLink.objects.filter(resident=user, id=request.POST.get("id")).delete()
        elif action == "remove_contact":
            EmergencyContact.objects.filter(resident=user, id=request.POST.get("id")).delete()
        elif action == "telegram_connect" and settings.TELEGRAM_BOT_USERNAME:
            user.telegram_link_token = secrets.token_urlsafe(24)
            user.save(update_fields=["telegram_link_token"])
            return redirect(f"https://t.me/{settings.TELEGRAM_BOT_USERNAME}"
                            f"?start={user.telegram_link_token}")
        elif action == "telegram_disconnect":
            user.telegram_chat_id = ""
            user.save(update_fields=["telegram_chat_id"])
        elif action == "revoke_invite":
            GuardianInvite.objects.filter(resident=user, id=request.POST.get("id"),
                                          accepted_by__isnull=True).delete()
        return redirect("circle")
    invites = GuardianInvite.objects.filter(resident=user, accepted_by__isnull=True)
    return render(request, "dashboard/circle.html", {
        "guardians": GuardianLink.objects.filter(resident=user).select_related("guardian"),
        "wards": GuardianLink.objects.filter(guardian=user).select_related("resident"),
        "contacts": EmergencyContact.objects.filter(resident=user),
        "invites": [(i, request.build_absolute_uri(f"/invite/{i.token}/")) for i in invites],
        "telegram_ready": bool(settings.TELEGRAM_BOT_TOKEN and settings.TELEGRAM_BOT_USERNAME),
    })


def invite(request, token):
    inv = (GuardianInvite.objects.filter(token=token, accepted_by__isnull=True)
           .select_related("resident").first())
    if request.method == "POST" and request.user.is_authenticated and inv:
        try:
            services.accept_invite(request.user, token)
            messages.success(request, f"You are now a guardian of {inv.resident.username}.")
            return redirect("board")
        except services.OnboardingError as exc:
            messages.error(request, str(exc))
    return render(request, "dashboard/invite.html", {"inv": inv, "token": token})
