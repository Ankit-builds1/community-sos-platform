from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie

DEMO_ACCOUNTS = [
    ("security_raju", "Security guard: sees every SOS in the society"),
    ("resident_ravi", "Resident: raises an SOS"),
    ("guardian_priya", "Primary guardian: alerted first"),
    ("volunteer_neha", "Volunteer: can accept and help"),
]


@login_required
@ensure_csrf_cookie  # the board's JavaScript needs the CSRF cookie for POST requests
def board(request):
    """Live incident board. Data comes from the REST API (session auth), polled every 5 s."""
    return render(request, "dashboard/board.html", {
        "can_raise": request.user.role == "resident",
    })

