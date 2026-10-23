from community.services import SANDBOX_ROLES


def nav(request):
    """Data for the shared nav bar and the sandbox role switcher."""
    users = request.session.get("sandbox_users") if hasattr(request, "session") else None
    user = getattr(request, "user", None)
    current = user.id if user and user.is_authenticated else None
    roles = [(key, label, users.get(key) == current) for key, label, _ in SANDBOX_ROLES] \
        if users else []
    return {"sandbox_roles": roles}
