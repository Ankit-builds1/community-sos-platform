from rest_framework import serializers

from .models import EmergencyContact, Flat, GuardianLink, Society, Tower


class FlatSerializer(serializers.ModelSerializer):
    class Meta:
        model = Flat
        fields = ["id", "number", "floor"]


class TowerSerializer(serializers.ModelSerializer):
    flats = FlatSerializer(many=True, read_only=True)

    class Meta:
        model = Tower
        fields = ["id", "name", "flats"]


class SocietySerializer(serializers.ModelSerializer):
    towers = TowerSerializer(many=True, read_only=True)

    class Meta:
        model = Society
        fields = ["id", "name", "address", "city", "latitude", "longitude", "towers"]


class GuardianLinkSerializer(serializers.ModelSerializer):
    guardian_username = serializers.CharField(source="guardian.username", read_only=True)

    class Meta:
        model = GuardianLink
        fields = ["id", "guardian", "guardian_username", "priority", "relation"]


class EmergencyContactSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmergencyContact
        fields = ["id", "name", "phone", "relation", "is_verified"]
        read_only_fields = ["is_verified"]
