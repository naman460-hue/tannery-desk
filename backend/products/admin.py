from django.contrib import admin

from .models import LeatherProduct


@admin.register(LeatherProduct)
class LeatherProductAdmin(admin.ModelAdmin):
    list_display = ("name", "factory", "leather_type", "application", "moq", "lead_time_days", "is_active")
    list_filter = ("leather_type", "application", "finish", "is_active")
    search_fields = ("name", "factory__name")
