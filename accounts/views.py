from django.conf import settings
from rest_framework import generics, permissions, status
from rest_framework.response import Response

from config.throttles import RegisterThrottle

from .serializers import RegisterSerializer, UserSerializer


class RegisterView(generics.CreateAPIView):
    """POST /api/auth/register/ - create a new account (no login needed).
    Disabled in DEMO_MODE: the public demo uses the fixed demo accounts only."""
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]
    throttle_classes = [RegisterThrottle]

    def create(self, request, *args, **kwargs):
        if settings.DEMO_MODE:
            return Response({"detail": "Sign-up is disabled in the public demo. "
                                       "Use a demo account (password Demo@1234)."},
                            status=status.HTTP_403_FORBIDDEN)
        return super().create(request, *args, **kwargs)


class MeView(generics.RetrieveUpdateAPIView):
    """GET / PATCH /api/auth/me/ - the logged-in user's own profile."""
    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user
