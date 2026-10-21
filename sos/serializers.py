from rest_framework import serializers

from .models import Alert, Incident


class AlertSerializer(serializers.ModelSerializer):
    recipient_username = serializers.CharField(source="recipient.username", read_only=True,
                                               default=None)

    class Meta:
        model = Alert
        fields = ["id", "recipient", "recipient_username", "recipient_phone", "audience",
                  "channel", "escalation_level", "status", "created_at", "responded_at"]


class RaiseSOSSerializer(serializers.Serializer):
    """Input for the SOS button. Everything is optional - one tap must always work."""
    category = serializers.ChoiceField(choices=Incident.Category.choices, default="other")
    message = serializers.CharField(required=False, allow_blank=True, default="")
    latitude = serializers.DecimalField(max_digits=9, decimal_places=6, required=False,
                                        allow_null=True, default=None)
    longitude = serializers.DecimalField(max_digits=9, decimal_places=6, required=False,
                                         allow_null=True, default=None)


class IncidentSerializer(serializers.ModelSerializer):
    resident_username = serializers.CharField(source="resident.username", read_only=True)
    alerts = AlertSerializer(many=True, read_only=True)

    class Meta:
        model = Incident
        fields = ["id", "resident", "resident_username", "society", "flat", "category",
                  "message", "latitude", "longitude", "status", "severity",
                  "escalation_level", "needs_human_review", "assigned_responder",
                  "created_at", "resolved_at",
                  "alerts"]
        read_only_fields = fields
