from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ("username", "email", "role", "phone", "is_available", "is_staff")
    list_filter = ("role", "is_available", "is_staff")
    fieldsets = UserAdmin.fieldsets + (
        ("SOS Platform", {"fields": ("role", "phone", "is_phone_verified", "is_available")}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("SOS Platform", {"fields": ("role", "phone")}),
    )
