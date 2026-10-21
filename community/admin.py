from django.contrib import admin

from .models import EmergencyContact, Flat, GuardianLink, Residency, Society, Tower


class TowerInline(admin.TabularInline):
    model = Tower
    extra = 1


class FlatInline(admin.TabularInline):
    model = Flat
    extra = 1


@admin.register(Society)
class SocietyAdmin(admin.ModelAdmin):
    list_display = ("name", "city", "created_at")
    search_fields = ("name", "city")
    inlines = [TowerInline]


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
