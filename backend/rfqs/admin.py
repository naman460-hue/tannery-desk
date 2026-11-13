from django.contrib import admin

from .models import FactoryQuotation, RFQ, RFQAttachment, RFQMatch


class MatchInline(admin.TabularInline):
    model = RFQMatch
    extra = 0


@admin.register(RFQ)
class RFQAdmin(admin.ModelAdmin):
    list_display = ("number", "client", "leather_type", "application", "quantity", "unit", "status", "created_at")
    list_filter = ("status", "leather_type", "application")
    search_fields = ("number", "client__email", "client__company_name")
    inlines = [MatchInline]


@admin.register(FactoryQuotation)
class QuotationAdmin(admin.ModelAdmin):
    list_display = ("id", "rfq", "factory", "price", "status", "validity_date")
    list_filter = ("status",)


admin.site.register(RFQAttachment)
