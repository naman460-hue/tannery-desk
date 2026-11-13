from rest_framework import serializers

from accounts.serializers import validate_phone_value
from common import choices
from common.validators import clean_filename, validate_document_upload

from .models import FactoryDocument, FactoryProfile


def string_list():
    return serializers.ListField(child=serializers.CharField(max_length=60), required=False, max_length=30)


class FactoryDocumentSerializer(serializers.ModelSerializer):
    file = serializers.FileField(write_only=True, validators=[validate_document_upload])
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = FactoryDocument
        fields = ("id", "kind", "title", "file", "original_name", "uploaded_at", "download_url")
        read_only_fields = ("id", "original_name", "uploaded_at", "download_url")

    def get_download_url(self, obj):
        return f"/api/factories/documents/{obj.pk}/download/"

    def create(self, validated):
        validated["original_name"] = clean_filename(validated["file"].name)
        return super().create(validated)


class FactoryPublicSerializer(serializers.ModelSerializer):
    """What clients and visitors can see. Contact details are deliberately left out."""

    documents = serializers.SerializerMethodField()

    class Meta:
        model = FactoryProfile
        fields = (
            "id", "name", "description", "city", "state", "country", "leather_types", "applications", "colors",
            "certifications", "min_thickness", "max_thickness", "min_order_quantity", "production_capacity",
            "typical_lead_time_days", "rating", "review_count", "verification_status", "documents",
        )
        read_only_fields = fields

    def get_documents(self, obj):
        return FactoryDocumentSerializer(obj.documents.filter(kind="CERTIFICATE"), many=True).data


class FactoryPrivateSerializer(serializers.ModelSerializer):
    """The factory's own profile (and what admins see)."""

    leather_types = string_list()
    applications = string_list()
    colors = string_list()
    certifications = string_list()
    documents = FactoryDocumentSerializer(many=True, read_only=True)
    is_profile_complete = serializers.BooleanField(read_only=True)
    owner_email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = FactoryProfile
        fields = (
            "id", "name", "description", "address", "city", "state", "country", "contact_name", "contact_phone",
            "contact_email", "leather_types", "applications", "colors", "certifications", "min_thickness",
            "max_thickness", "min_order_quantity", "production_capacity", "typical_lead_time_days",
            "verification_status", "verification_note", "rating", "review_count", "documents",
            "is_profile_complete", "owner_email", "created_at",
        )
        read_only_fields = ("id", "verification_status", "verification_note", "rating", "review_count",
                            "documents", "is_profile_complete", "owner_email", "created_at")

    @staticmethod
    def _subset(values, allowed, label):
        bad = [v for v in values if v not in allowed]
        if bad:
            raise serializers.ValidationError(f"Unknown {label}: {', '.join(bad)}.")
        return values

    def validate_leather_types(self, value):
        return self._subset(value, choices.LEATHER_TYPES, "leather type")

    def validate_applications(self, value):
        return self._subset(value, choices.APPLICATIONS, "application")

    def validate_colors(self, value):
        return self._subset(value, list(choices.COLORS), "color")

    def validate_contact_phone(self, value):
        return validate_phone_value(value)

    def validate_min_order_quantity(self, value):
        if value is not None and value <= 0:
            raise serializers.ValidationError("Minimum order quantity must be more than zero.")
        return value

    def validate_production_capacity(self, value):
        if value is not None and value <= 0:
            raise serializers.ValidationError("Production capacity must be more than zero.")
        return value

    def validate(self, attrs):
        lo = attrs.get("min_thickness", getattr(self.instance, "min_thickness", None))
        hi = attrs.get("max_thickness", getattr(self.instance, "max_thickness", None))
        if lo is not None and hi is not None and lo > hi:
            raise serializers.ValidationError({"max_thickness": ["Maximum thickness must be at least the minimum."]})
        return attrs
