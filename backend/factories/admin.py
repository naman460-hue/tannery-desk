from django.contrib import admin

from .models import FactoryDocument, FactoryProfile


@admin.register(FactoryProfile)
class FactoryProfileAdmin(admin.ModelAdmin):
    list_display = ("name", "city", "state", "verification_status", "rating", "review_count", "created_at")
    list_filter = ("verification_status", "state")
    search_fields = ("name", "city", "user__email")


admin.site.register(FactoryDocument)
