from rest_framework import serializers

from common import choices
from common.validators import validate_image_upload

from .models import LeatherProduct


class ProductSerializer(serializers.ModelSerializer):
    certifications = serializers.ListField(child=serializers.CharField(max_length=60), required=False, max_length=10,
                                           write_only=True)
    image = serializers.ImageField(required=False, allow_null=True, validators=[validate_image_upload])
    color_hex = serializers.SerializerMethodField()
    unit_label = serializers.SerializerMethodField()
    thickness_display = serializers.SerializerMethodField()
    factory = serializers.SerializerMethodField()

    class Meta:
        model = LeatherProduct
        fields = (
            "id", "name", "leather_type", "finish", "application", "color", "thickness_min", "thickness_max",
            "thickness_display", "moq", "unit", "unit_label", "lead_time_days", "certifications", "description",
            "image", "sample_available", "is_active", "color_hex", "factory", "created_at",
        )
        read_only_fields = ("id", "created_at", "color_hex", "unit_label", "thickness_display", "factory")

    def get_color_hex(self, obj):
        return choices.COLORS.get(obj.color, "#9A8B7A")

    def get_unit_label(self, obj):
        return choices.unit_label(obj.unit)

    def get_thickness_display(self, obj):
        return f"{obj.thickness_min:g}–{obj.thickness_max:g} mm"

    def get_factory(self, obj):
        f = obj.factory
        return {"id": f.id, "name": f.name, "city": f.city, "state": f.state, "rating": str(f.rating),
                "review_count": f.review_count, "verified": f.verification_status == "VERIFIED"}

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["certifications"] = instance.certification_list
        return data

    @staticmethod
    def _in(value, allowed, label):
        if value not in allowed:
            raise serializers.ValidationError(f"Please select a valid {label}.")
        return value

    def validate_leather_type(self, value):
        return self._in(value, choices.LEATHER_TYPES, "leather type")

    def validate_finish(self, value):
        return self._in(value, choices.FINISHES, "finish")

    def validate_application(self, value):
        return self._in(value, choices.APPLICATIONS, "application")

    def validate_color(self, value):
        return self._in(value, list(choices.COLORS), "color")

    def validate_unit(self, value):
        return self._in(value, dict(choices.UNITS), "unit")

    def validate_moq(self, value):
        if value <= 0:
            raise serializers.ValidationError("Minimum order quantity must be more than zero.")
        return value

    def validate_lead_time_days(self, value):
        if value < 1 or value > 365:
            raise serializers.ValidationError("Lead time must be between 1 and 365 days.")
        return value

    def validate(self, attrs):
        lo = attrs.get("thickness_min", getattr(self.instance, "thickness_min", None))
        hi = attrs.get("thickness_max", getattr(self.instance, "thickness_max", None))
        if lo is not None and hi is not None and lo > hi:
            raise serializers.ValidationError({"thickness_max": ["Maximum thickness must be at least the minimum."]})
        if "certifications" in attrs:
            attrs["certifications"] = ", ".join(attrs["certifications"])
        return attrs
