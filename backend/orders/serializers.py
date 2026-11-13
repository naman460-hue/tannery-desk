from rest_framework import serializers

from common import choices
from common.utils import today
from common.validators import clean_filename, validate_document_upload

from .models import Dispute, Order, OrderDocument, ProductionUpdate
from .services import next_payment

PRODUCTION_STAGES = ["PRODUCTION_STARTED", "QUALITY_CHECK", "PACKAGING", "IN_TRANSIT", "DELIVERED"]


def _future_date(value):
    if value < today():
        raise serializers.ValidationError("Expected delivery cannot be in the past.")
    return value


class ProductionUpdateSerializer(serializers.ModelSerializer):
    stage_label = serializers.CharField(source="get_stage_display", read_only=True)
    updated_by_name = serializers.CharField(source="updated_by.name", read_only=True, default="")

    class Meta:
        model = ProductionUpdate
        fields = ("id", "stage", "stage_label", "percentage", "message", "updated_by_name", "created_at")
        read_only_fields = fields


class ProductionInputSerializer(serializers.Serializer):
    stage = serializers.ChoiceField(choices=PRODUCTION_STAGES)
    percentage = serializers.IntegerField(min_value=0, max_value=100)
    message = serializers.CharField(max_length=500, required=False, allow_blank=True)


class DispatchInputSerializer(serializers.Serializer):
    courier_name = serializers.CharField(max_length=100)
    tracking_number = serializers.CharField(max_length=100)
    expected_delivery = serializers.DateField(required=False)
    validate_expected_delivery = staticmethod(_future_date)


class DeliveryDateSerializer(serializers.Serializer):
    expected_delivery = serializers.DateField()
    message = serializers.CharField(max_length=300, required=False, allow_blank=True)
    validate_expected_delivery = staticmethod(_future_date)


class OrderDocumentSerializer(serializers.ModelSerializer):
    file = serializers.FileField(write_only=True, validators=[validate_document_upload])
    download_url = serializers.SerializerMethodField()
    uploaded_by_name = serializers.CharField(source="uploaded_by.name", read_only=True, default="")

    class Meta:
        model = OrderDocument
        fields = ("id", "kind", "title", "file", "original_name", "download_url", "uploaded_by_name", "created_at")
        read_only_fields = ("id", "original_name", "download_url", "uploaded_by_name", "created_at")

    def get_download_url(self, obj):
        return f"/api/orders/documents/{obj.pk}/download/"

    def create(self, validated):
        validated["original_name"] = clean_filename(validated["file"].name)
        return super().create(validated)


class OrderSerializer(serializers.ModelSerializer):
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    payment_status_label = serializers.CharField(source="get_payment_status_display", read_only=True)
    rfq_id = serializers.IntegerField(read_only=True)
    rfq_number = serializers.CharField(source="rfq.number", read_only=True)
    title = serializers.CharField(source="rfq.title", read_only=True)
    quantity = serializers.DecimalField(source="quotation.quantity", max_digits=12, decimal_places=2, read_only=True)
    unit_label = serializers.SerializerMethodField()
    price = serializers.DecimalField(source="quotation.price", max_digits=12, decimal_places=2, read_only=True)
    factory_name = serializers.CharField(source="factory.name", read_only=True)
    client_name = serializers.SerializerMethodField()
    latest_update = serializers.SerializerMethodField()
    next_payment = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = (
            "id", "number", "rfq_id", "rfq_number", "title", "quantity", "unit_label", "price", "factory_name",
            "client_name", "total_amount", "advance_amount", "remaining_amount", "payment_status",
            "payment_status_label", "status", "status_label", "progress_percent", "expected_completion",
            "expected_delivery", "ready_for_dispatch", "courier_name", "tracking_number", "dispatched_at",
            "delivered_at", "latest_update", "next_payment", "created_at",
        )
        read_only_fields = fields

    def get_unit_label(self, obj):
        return choices.unit_label(obj.quotation.price_unit)

    def get_client_name(self, obj):
        return obj.client.company_name or obj.client.name

    def get_latest_update(self, obj):
        update = obj.updates.first()
        return update and {"stage": update.get_stage_display(), "message": update.message, "created_at": update.created_at}

    def get_next_payment(self, obj):
        request = self.context.get("request")
        if request is not None and request.user.role != "CLIENT":
            return None
        return next_payment(obj)


class OrderDetailSerializer(OrderSerializer):
    updates = ProductionUpdateSerializer(many=True, read_only=True)
    documents = OrderDocumentSerializer(many=True, read_only=True)
    payments = serializers.SerializerMethodField()
    review = serializers.SerializerMethodField()
    parties = serializers.SerializerMethodField()
    quotation_notes = serializers.CharField(source="quotation.notes", read_only=True)
    production_days = serializers.IntegerField(source="quotation.production_days", read_only=True)
    shipping_days = serializers.IntegerField(source="quotation.shipping_days", read_only=True)
    open_disputes = serializers.SerializerMethodField()

    class Meta(OrderSerializer.Meta):
        fields = OrderSerializer.Meta.fields + (
            "updates", "documents", "payments", "review", "parties", "quotation_notes", "production_days",
            "shipping_days", "open_disputes",
        )
        read_only_fields = fields

    def get_payments(self, obj):
        from payments.serializers import PaymentSerializer

        qs = obj.payments.all()
        if self.context["request"].user.role == "FACTORY":
            qs = qs.filter(status="PAID")
        return PaymentSerializer(qs, many=True).data

    def get_review(self, obj):
        review = getattr(obj, "review", None)
        return review and {"rating": review.rating, "review": review.review, "created_at": review.created_at}

    def get_open_disputes(self, obj):
        return obj.disputes.exclude(status__in=["RESOLVED", "CLOSED"]).count()

    def get_parties(self, obj):
        """Contact details appear only once an order exists, and only to the people involved."""
        role = self.context["request"].user.role
        out = {}
        if role in ("FACTORY", "ADMIN"):
            c = obj.client
            out["client"] = {"name": c.name, "company_name": c.company_name, "phone": c.phone, "email": c.email,
                             "address": c.address, "city": c.city, "state": c.state}
        if role in ("CLIENT", "ADMIN"):
            f = obj.factory
            out["factory"] = {"id": f.id, "name": f.name, "contact_name": f.contact_name, "phone": f.contact_phone,
                              "email": f.contact_email, "city": f.city, "state": f.state}
        return out


class DisputeSerializer(serializers.ModelSerializer):
    order_number = serializers.CharField(source="order.number", read_only=True)
    raised_by_name = serializers.CharField(source="raised_by.name", read_only=True)
    raised_by_role = serializers.CharField(source="raised_by.role", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Dispute
        fields = ("id", "order", "order_number", "raised_by_name", "raised_by_role", "subject", "description",
                  "status", "status_label", "resolution", "created_at", "updated_at")
        read_only_fields = ("id", "status", "resolution", "created_at", "updated_at")
