from django.db.models import Q
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Incident
from .serializers import IncidentSerializer, RaiseSOSSerializer
from .services import (SOSActionError, accept_incident, decline_incident, raise_sos,
                       resolve_incident)


class IncidentViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET  /api/incidents/               incidents I raised or was alerted about
    GET  /api/incidents/<id>/          one incident with its alerts
    POST /api/incidents/raise/         the SOS button
    POST /api/incidents/<id>/accept/   I'm going to help
    POST /api/incidents/<id>/decline/  I can't help
    POST /api/incidents/<id>/resolve/  help given, incident over
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

    def _run(self, func, request):
        try:
            incident = func(self.get_object(), request.user)
        except SOSActionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        incident.refresh_from_db()
        return Response(IncidentSerializer(incident).data)

    @action(detail=True, methods=["post"])
    def accept(self, request, pk=None):
        return self._run(accept_incident, request)

    @action(detail=True, methods=["post"])
    def decline(self, request, pk=None):
        return self._run(decline_incident, request)

    @action(detail=True, methods=["post"])
    def resolve(self, request, pk=None):
        return self._run(resolve_incident, request)

    @action(detail=True, methods=["get"], url_path="first-aid")
    def first_aid(self, request, pk=None):
        """GET /api/incidents/<id>/first-aid/  - RAG first-aid steps for this incident.
        Uses the resident's original message (query rewriting translates it to English).
        Only an empty one-tap SOS falls back to the triage summary or the category."""
        from firstaid.assistant import answer

        incident = self.get_object()
        query = incident.message or incident.guardian_summary or incident.category
        return Response({"incident": incident.pk, "query": query,
                         **answer(query, is_sos=True)})
