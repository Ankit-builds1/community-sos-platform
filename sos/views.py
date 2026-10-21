from django.db.models import Q
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Incident
from .serializers import IncidentSerializer, RaiseSOSSerializer
from .services import raise_sos


class IncidentViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET  /api/incidents/          incidents I raised or was alerted about
    GET  /api/incidents/<id>/     one incident with its alerts
    POST /api/incidents/raise/    the SOS button
    """
    serializer_class = IncidentSerializer

    def get_queryset(self):
        user = self.request.user
        qs = Incident.objects.prefetch_related("alerts__recipient")
        if user.is_staff:
            return qs
        return qs.filter(Q(resident=user) | Q(alerts__recipient=user)).distinct()

    @action(detail=False, methods=["post"], url_path="raise",
            serializer_class=RaiseSOSSerializer)
    def raise_(self, request):
        data = RaiseSOSSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        incident = raise_sos(request.user, **data.validated_data)
        return Response(IncidentSerializer(incident).data, status=status.HTTP_201_CREATED)
