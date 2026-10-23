"""Rate limits for expensive or abusable endpoints."""
from django.conf import settings
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle


class SOSRaiseThrottle(UserRateThrottle):
    """Applied ONLY in demo mode. In a real deployment an SOS must never be blocked,
    so there the Groq quota is protected by the daily LLM budget instead."""
    scope = "sos_raise"

    def allow_request(self, request, view):
        if not settings.DEMO_MODE:
            return True
        return super().allow_request(request, view)


class FirstAidThrottle(UserRateThrottle):
    scope = "first_aid"


class RegisterThrottle(AnonRateThrottle):
    scope = "register"
