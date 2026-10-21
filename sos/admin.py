from django.contrib import admin

from .models import Alert, Incident


class AlertInline(admin.TabularInline):
    model = Alert
    extra = 0
    readonly_fields = ("created_at", "responded_at")


@admin.register(Incident)
class IncidentAdmin(admin.ModelAdmin):
    list_display = ("id", "resident", "category", "severity", "triage_source", "status",
                    "escalation_level", "needs_human_review", "injection_suspected",
                    "assigned_responder", "created_at")
    list_filter = ("status", "needs_human_review", "category", "severity", "society")
    search_fields = ("resident__username", "message")
    inlines = [AlertInline]


@admin.register(Alert)
class AlertAdmin(admin.ModelAdmin):
    list_display = ("incident", "recipient", "recipient_phone", "audience", "channel",
                    "escalation_level", "status", "created_at")
    list_filter = ("audience", "channel", "status")
