from django.contrib import admin

from .models import Dispute, Order, OrderDocument, ProductionUpdate


class UpdateInline(admin.TabularInline):
    model = ProductionUpdate
    extra = 0


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("number", "client", "factory", "total_amount", "payment_status", "status", "created_at")
    list_filter = ("status", "payment_status")
    search_fields = ("number", "client__email", "factory__name")
    inlines = [UpdateInline]


@admin.register(Dispute)
class DisputeAdmin(admin.ModelAdmin):
    list_display = ("id", "order", "raised_by", "subject", "status", "created_at")
    list_filter = ("status",)


admin.site.register(OrderDocument)
