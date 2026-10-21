from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from .models import User

# Roles a person may pick when signing up. Admin / Security are created by an admin.
SELF_SIGNUP_ROLES = [User.Role.RESIDENT, User.Role.GUARDIAN, User.Role.VOLUNTEER]


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])
    role = serializers.ChoiceField(choices=SELF_SIGNUP_ROLES, default=User.Role.RESIDENT)

    class Meta:
        model = User
        fields = ["id", "username", "email", "password", "first_name", "last_name",
                  "phone", "role"]

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "email", "first_name", "last_name", "phone",
                  "role", "is_phone_verified", "is_available"]
        read_only_fields = ["id", "username", "role", "is_phone_verified"]
