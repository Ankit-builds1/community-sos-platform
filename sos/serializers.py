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
    category = serializers.ChoiceField(choices=Incident.Category.choices, default="other",
                                       allow_null=True)
    message = serializers.CharField(required=False, allow_blank=True, allow_null=True,
                                    default="")
    latitude = serializers.DecimalField(max_digits=9, decimal_places=6, required=False,
                                        allow_null=True, default=None)
    longitude = serializers.DecimalField(max_digits=9, decimal_places=6, required=False,
                                         allow_null=True, default=None)

    def validate(self, attrs):
        # An SOS must never be rejected over a missing field: null -> safe defaults.
        attrs["category"] = attrs.get("category") or "other"
        attrs["message"] = attrs.get("message") or ""
        return attrs


class IncidentSerializer(serializers.ModelSerializer):
    resident_username = serializers.CharField(source="resident.username", read_only=True)
    alerts = AlertSerializer(many=True, read_only=True)
    # display fields for the dashboard
    location = serializers.SerializerMethodField()
    assigned_responder_username = serializers.CharField(
        source="assigned_responder.username", read_only=True, default=None)

    def get_location(self, obj):
        if obj.flat_id:
            return f"{obj.flat.tower.name} · Flat {obj.flat.number}"
        return obj.society.name if obj.society_id else "Unknown location"

    map_point = serializers.SerializerMethodField()

    def get_map_point(self, obj):
        """Where to drop the pin: the phone's GPS if shared, else the society's address."""
        if obj.latitude is not None and obj.longitude is not None:
            return {"lat": float(obj.latitude), "lng": float(obj.longitude), "source": "gps"}
        s = obj.society
        if s and s.latitude is not None and s.longitude is not None:
            return {"lat": float(s.latitude), "lng": float(s.longitude), "source": "society"}
        return None

    class Meta:
        model = Incident
        fields = ["id", "resident", "resident_username", "society", "flat", "category",
                  "message", "latitude", "longitude", "status", "severity",
                  "guardian_summary", "triage_confidence", "triage_source",
                  "injection_suspected", "triaged_at",
                  "escalation_level", "needs_human_review", "assigned_responder",
                  "assigned_responder_username", "location", "map_point",
                  "created_at", "resolved_at",
                  "alerts"]
        read_only_fields = fields
