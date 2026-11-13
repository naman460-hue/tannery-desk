from rest_framework import serializers

from common import choices
from common.utils import today
from common.validators import clean_filename, validate_document_upload
from products.models import LeatherProduct

from .models import FactoryQuotation, RFQ, RFQAttachment, RFQMatch


class RFQAttachmentSerializer(serializers.ModelSerializer):
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = RFQAttachment
        fields = ("id", "original_name", "created_at", "download_url")
        read_only_fields = fields

    def get_download_url(self, obj):
        return f"/api/rfqs/attachments/{obj.pk}/download/"


class AttachmentUploadSerializer(serializers.Serializer):
    file = serializers.FileField(validators=[validate_document_upload])


class RFQSerializer(serializers.ModelSerializer):
    client_token = serializers.CharField(write_only=True, required=False, allow_blank=True, max_length=64)
    product = serializers.PrimaryKeyRelatedField(queryset=LeatherProduct.objects.all(), required=False, allow_null=True)
    required_certifications = serializers.ListField(child=serializers.CharField(max_length=60), required=False,
                                                    max_length=10)
    attachments = RFQAttachmentSerializer(many=True, read_only=True)
    title = serializers.CharField(read_only=True)
    unit_label = serializers.SerializerMethodField()
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    quotation_count = serializers.SerializerMethodField()

    class Meta:
        model = RFQ
        fields = (
            "id", "number", "client_token", "product", "need", "leather_type", "application", "finish", "color",
            "thickness_min", "thickness_max", "quantity", "unit", "unit_label", "requirements", "target_price",
            "required_date", "delivery_city", "delivery_state", "required_certifications", "status", "status_label",
            "title", "attachments", "quotation_count", "created_at",
        )
        read_only_fields = ("id", "number", "status", "created_at")
        validators = []
        extra_kwargs = {
            "need": {"required": False, "allow_blank": True},
            "finish": {"required": False, "allow_blank": True},
            "requirements": {"required": False, "allow_blank": True},
            "delivery_city": {"required": False, "allow_blank": True},
            "delivery_state": {"required": False, "allow_blank": True},
        }

    def get_unit_label(self, obj):
        return choices.unit_label(obj.unit)

    def get_quotation_count(self, obj):
        return obj.quotations.exclude(status="WITHDRAWN").count()

    @staticmethod
    def _in(value, allowed, message):
        if value not in allowed:
            raise serializers.ValidationError(message)
        return value

    def validate_leather_type(self, value):
        return self._in(value, choices.LEATHER_TYPES, "Please select a leather type.")

    def validate_application(self, value):
        return self._in(value, choices.APPLICATIONS, "Please select an application.")

    def validate_finish(self, value):
        return value if not value else self._in(value, choices.FINISHES, "Please select a valid finish.")

    def validate_color(self, value):
        return self._in(value, list(choices.COLORS), "Please select a color.")

    def validate_need(self, value):
        return value if not value else self._in(value, choices.NEEDS, "Please select what you need.")

    def validate_unit(self, value):
        return self._in(value, dict(choices.UNITS), "Please select a unit.")

    def validate_quantity(self, value):
        if value <= 0:
            raise serializers.ValidationError("Quantity must be more than zero.")
        return value

    def validate_target_price(self, value):
        if value is not None and value <= 0:
            raise serializers.ValidationError("Target price must be more than zero, or leave it empty.")
        return value

    def validate_required_date(self, value):
        if value <= today():
            raise serializers.ValidationError("Please choose a delivery date in the future.")
        return value

    def validate_requirements(self, value):
        if len(value) > 2000:
            raise serializers.ValidationError("Please keep notes under 2000 characters.")
        return value

    def validate(self, attrs):
        lo = attrs.get("thickness_min", getattr(self.instance, "thickness_min", None))
        hi = attrs.get("thickness_max", getattr(self.instance, "thickness_max", None))
        if lo is not None and hi is not None and lo > hi:
            raise serializers.ValidationError({"thickness_max": ["Maximum thickness must be at least the minimum."]})
        return attrs

    def to_representation(self, instance):
        """Who sees what: factories do not see who the buyer is until an order exists."""
        data = super().to_representation(instance)
        request = self.context.get("request")
        role = getattr(getattr(request, "user", None), "role", None)
        client = instance.client
        if role == "FACTORY":
            fp = request.user.factory_profile
            match = next((m for m in instance.matches.all() if m.factory_id == fp.id), None)
            data["my_match"] = match and {"response": match.response, "score": match.score, "reasons": match.reasons}
            data["client_city"] = client.city
        elif role == "ADMIN":
            data["client"] = {"id": client.id, "name": client.name, "company_name": client.company_name,
                              "email": client.email, "phone": client.phone, "city": client.city}
            data["matches"] = [
                {"factory_id": m.factory_id, "factory_user_id": m.factory.user_id, "factory_name": m.factory.name, "score": m.score,
                 "response": m.response, "assigned_by_admin": m.assigned_by_admin}
                for m in instance.matches.all()
            ]
        else:
            data["client_city"] = client.city
        return data


class FactorySummarySerializer(serializers.Serializer):
    def to_representation(self, f):
        return {
            "id": f.id, "user_id": f.user_id, "name": f.name, "city": f.city, "state": f.state, "rating": str(f.rating),
            "review_count": f.review_count, "certifications": f.certifications or [],
            "min_order_quantity": f.min_order_quantity, "typical_lead_time_days": f.typical_lead_time_days,
        }


class QuotationSerializer(serializers.ModelSerializer):
    rfq = serializers.PrimaryKeyRelatedField(queryset=RFQ.objects.all())
    attachment = serializers.FileField(write_only=True, required=False, allow_null=True,
                                       validators=[validate_document_upload])
    total_amount = serializers.DecimalField(max_digits=16, decimal_places=2, read_only=True)
    lead_time_days = serializers.IntegerField(read_only=True)
    unit_label = serializers.SerializerMethodField()
    rfq_number = serializers.CharField(source="rfq.number", read_only=True)
    rfq_title = serializers.CharField(source="rfq.title", read_only=True)
    factory = FactorySummarySerializer(read_only=True)
    attachment_url = serializers.SerializerMethodField()
    match_score = serializers.SerializerMethodField()
    match_reasons = serializers.SerializerMethodField()
    recommended = serializers.SerializerMethodField()

    class Meta:
        model = FactoryQuotation
        fields = (
            "id", "rfq", "rfq_number", "rfq_title", "factory", "price", "price_unit", "unit_label", "quantity", "moq",
            "production_days", "shipping_days", "lead_time_days", "total_amount", "notes", "validity_date",
            "attachment", "attachment_url", "attachment_name", "status", "match_score", "match_reasons",
            "recommended", "created_at", "updated_at",
        )
        read_only_fields = ("id", "factory", "price_unit", "status", "attachment_name", "created_at", "updated_at")
        validators = []

    def get_unit_label(self, obj):
        return choices.unit_label(obj.price_unit)

    def get_attachment_url(self, obj):
        return f"/api/quotations/{obj.pk}/attachment/" if obj.attachment else None

    def _match(self, obj):
        if not hasattr(obj, "_match_cache"):
            obj._match_cache = RFQMatch.objects.filter(rfq_id=obj.rfq_id, factory_id=obj.factory_id).first()
        return obj._match_cache

    def get_match_score(self, obj):
        m = self._match(obj)
        return m.score if m else None

    def get_match_reasons(self, obj):
        m = self._match(obj)
        return m.reasons if m else []

    def get_recommended(self, obj):
        return bool(getattr(obj, "_recommended", False))

    def validate_price(self, value):
        if value <= 0:
            raise serializers.ValidationError("Price must be more than zero.")
        return value

    def validate_quantity(self, value):
        if value <= 0:
            raise serializers.ValidationError("Quantity must be more than zero.")
        return value

    def validate_moq(self, value):
        if value is not None and value <= 0:
            raise serializers.ValidationError("Minimum order quantity must be more than zero.")
        return value

    def validate_production_days(self, value):
        if value < 1 or value > 365:
            raise serializers.ValidationError("Production time must be between 1 and 365 days.")
        return value

    def validate_shipping_days(self, value):
        if value > 365:
            raise serializers.ValidationError("Shipping time must be 365 days or less.")
        return value

    def validate_validity_date(self, value):
        if value < today():
            raise serializers.ValidationError("The quotation validity date cannot be in the past.")
        return value

    def validate_notes(self, value):
        if len(value) > 1500:
            raise serializers.ValidationError("Please keep notes under 1500 characters.")
        return value

    def create(self, validated):
        upload = validated.get("attachment")
        if upload:
            validated["attachment_name"] = clean_filename(upload.name)
        return super().create(validated)

    def update(self, instance, validated):
        validated.pop("rfq", None)
        upload = validated.get("attachment")
        if upload:
            validated["attachment_name"] = clean_filename(upload.name)
        return super().update(instance, validated)
