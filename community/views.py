from rest_framework import viewsets

from .models import EmergencyContact, GuardianLink, Society
from .serializers import (EmergencyContactSerializer, GuardianLinkSerializer,
                          SocietySerializer)


class SocietyViewSet(viewsets.ReadOnlyModelViewSet):
    """GET /api/societies/ - societies with their towers and flats."""
    queryset = Society.objects.prefetch_related("towers__flats")
    serializer_class = SocietySerializer


class MyGuardiansViewSet(viewsets.ModelViewSet):
    """/api/my/guardians/ - the logged-in resident manages their own guardians."""
    serializer_class = GuardianLinkSerializer

    def get_queryset(self):
        return GuardianLink.objects.filter(resident=self.request.user)

    def perform_create(self, serializer):
        serializer.save(resident=self.request.user)


class MyEmergencyContactsViewSet(viewsets.ModelViewSet):
    """/api/my/emergency-contacts/ - the logged-in resident's emergency contacts."""
    serializer_class = EmergencyContactSerializer

    def get_queryset(self):
        return EmergencyContact.objects.filter(resident=self.request.user)

    def perform_create(self, serializer):
        serializer.save(resident=self.request.user)
