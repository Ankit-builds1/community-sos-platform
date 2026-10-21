from rest_framework import generics, permissions

from .serializers import RegisterSerializer, UserSerializer


class RegisterView(generics.CreateAPIView):
    """POST /api/auth/register/ - create a new account (no login needed)."""
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]


class MeView(generics.RetrieveUpdateAPIView):
    """GET / PATCH /api/auth/me/ - the logged-in user's own profile."""
    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user
