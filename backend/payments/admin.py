from django.contrib import admin

from .models import Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("id", "order", "purpose", "amount", "status", "mode", "created_at", "paid_at")
    list_filter = ("status", "mode", "purpose")
    search_fields = ("razorpay_order_id", "razorpay_payment_id", "order__number")
    readonly_fields = ("razorpay_signature",)
