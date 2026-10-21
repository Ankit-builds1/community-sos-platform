from django.contrib import admin

from .models import Alert, Incident


class AlertInline(admin.TabularInline):
    model = Alert
    extra = 0
    readonly_fields = ("created_at", "responded_at")


@admin.register(Incident)
class IncidentAdmin(admin.ModelAdmin):
    list_display = ("id", "resident", "category", "severity", "status", "escalation_level",
                    "society", "created_at")
    list_filter = ("status", "category", "severity", "society")
    search_fields = ("resident__username", "message")
    inlines = [AlertInline]


@admin.register(Alert)
class AlertAdmin(admin.ModelAdmin):
    list_display = ("incident", "recipient", "recipient_phone", "audience", "channel",
                    "escalation_level", "status", "created_at")
    list_filter = ("audience", "channel", "status")
