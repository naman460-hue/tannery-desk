from rest_framework import serializers

from .models import Payment


class PaymentSerializer(serializers.ModelSerializer):
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    purpose_label = serializers.CharField(source="get_purpose_display", read_only=True)
    mode_label = serializers.CharField(source="get_mode_display", read_only=True)
    receipt_number = serializers.CharField(read_only=True)
    order_number = serializers.CharField(source="order.number", read_only=True)
    payer_name = serializers.SerializerMethodField()

    class Meta:
        model = Payment
        fields = ("id", "order", "order_number", "payer_name", "purpose", "purpose_label", "amount", "currency",
                  "status", "status_label", "mode", "mode_label", "razorpay_order_id", "razorpay_payment_id",
                  "failure_reason", "receipt_number", "created_at", "paid_at")
        read_only_fields = fields

    def get_payer_name(self, obj):
        return obj.payer.company_name or obj.payer.name
