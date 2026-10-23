from django.contrib import admin

from .models import (EmergencyContact, Flat, GuardianInvite, GuardianLink, JoinRequest,
                     Residency, Society, Tower)


class TowerInline(admin.TabularInline):
    model = Tower
    extra = 1


class FlatInline(admin.TabularInline):
    model = Flat
    extra = 1


@admin.register(Society)
class SocietyAdmin(admin.ModelAdmin):
    list_display = ("name", "city", "status", "join_code", "is_sandbox", "created_by", "created_at")
    list_filter = ("status", "is_sandbox")
    search_fields = ("name", "city", "join_code")
    inlines = [TowerInline]
    actions = ["approve", "reject"]

    @admin.action(description="Approve selected societies")
    def approve(self, request, queryset):
        for s in queryset:
            s.status = Society.Status.APPROVED
            s.save(update_fields=["status"])
            s.ensure_join_code()

    @admin.action(description="Reject selected societies")
    def reject(self, request, queryset):
        queryset.update(status=Society.Status.REJECTED)


@admin.register(JoinRequest)
class JoinRequestAdmin(admin.ModelAdmin):
    list_display = ("user", "society", "role", "flat", "status", "created_at")
    list_filter = ("status", "role")


@admin.register(GuardianInvite)
class GuardianInviteAdmin(admin.ModelAdmin):
    list_display = ("resident", "priority", "relation", "accepted_by", "created_at")


@admin.register(Tower)
class TowerAdmin(admin.ModelAdmin):
    list_display = ("name", "society")
    list_filter = ("society",)
    inlines = [FlatInline]


@admin.register(Flat)
class FlatAdmin(admin.ModelAdmin):
    list_display = ("number", "floor", "tower")
    list_filter = ("tower__society",)


@admin.register(Residency)
class ResidencyAdmin(admin.ModelAdmin):
    list_display = ("user", "society", "flat")
    list_filter = ("society",)


@admin.register(GuardianLink)
class GuardianLinkAdmin(admin.ModelAdmin):
    list_display = ("resident", "guardian", "priority", "relation")


@admin.register(EmergencyContact)
class EmergencyContactAdmin(admin.ModelAdmin):
    list_display = ("name", "phone", "relation", "resident", "is_verified")
