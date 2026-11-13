from django.contrib import admin

from .models import Message


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("id", "sender", "rfq", "order", "created_at")
    search_fields = ("body", "sender__email")
