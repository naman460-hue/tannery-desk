from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import ClientProfile, User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    ordering = ("-created_at",)
    list_display = ("email", "name", "role", "company_name", "is_active", "is_demo", "created_at")
    list_filter = ("role", "is_active", "is_demo")
    search_fields = ("email", "name", "company_name", "phone")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Details", {"fields": ("name", "phone", "role", "company_name", "address", "city", "state", "country", "is_demo")}),
        ("Access", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
    )
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("email", "name", "role", "password1", "password2")}),)


admin.site.register(ClientProfile)
