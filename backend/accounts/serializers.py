import re

from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from rest_framework import serializers

from .models import ClientProfile, Role, User

PHONE_RE = re.compile(r"^\+?[0-9][0-9\s\-]{7,17}$")


def validate_phone_value(value):
    value = (value or "").strip()
    if value and not PHONE_RE.match(value):
        raise serializers.ValidationError("Please enter a valid phone number, for example +91 98765 43210.")
    return value


def _password_errors(password, user):
    try:
        validate_password(password, user=user)
    except Exception as exc:  # django ValidationError carries .messages
        return list(getattr(exc, "messages", [str(exc)]))
    return []


class RegisterSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    phone = serializers.CharField(max_length=20)
    password = serializers.CharField(write_only=True, trim_whitespace=False)
    confirm_password = serializers.CharField(write_only=True, trim_whitespace=False)
    role = serializers.ChoiceField(choices=[Role.CLIENT, Role.FACTORY])
    company_name = serializers.CharField(max_length=200, required=False, allow_blank=True)
    city = serializers.CharField(max_length=100, required=False, allow_blank=True)
    state = serializers.CharField(max_length=100, required=False, allow_blank=True)
    address = serializers.CharField(max_length=300, required=False, allow_blank=True)

    def validate_email(self, value):
        value = value.strip().lower()
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("An account with this email already exists. Please sign in instead.")
        return value

    def validate_phone(self, value):
        return validate_phone_value(value)

    def validate(self, attrs):
        if attrs["password"] != attrs["confirm_password"]:
            raise serializers.ValidationError({"confirm_password": ["The two passwords do not match."]})
        errors = _password_errors(attrs["password"], User(name=attrs["name"], email=attrs["email"]))
        if errors:
            raise serializers.ValidationError({"password": errors})
        if attrs["role"] == Role.FACTORY and not attrs.get("company_name", "").strip():
            raise serializers.ValidationError({"company_name": ["Please enter your factory name."]})
        return attrs

    @transaction.atomic
    def create(self, validated):
        from factories.models import FactoryProfile

        validated.pop("confirm_password")
        password = validated.pop("password")
        role = validated["role"]
        user = User.objects.create_user(password=password, **validated)
        if role == Role.CLIENT:
            ClientProfile.objects.create(user=user)
        else:
            FactoryProfile.objects.create(
                user=user, name=user.company_name, city=user.city, state=user.state, address=user.address,
                contact_name=user.name, contact_phone=user.phone, contact_email=user.email,
            )
        return user


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(trim_whitespace=False)
    portal = serializers.ChoiceField(choices=Role.values, required=False)


class ClientProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClientProfile
        fields = ("gst_number", "industry")


class UserSerializer(serializers.ModelSerializer):
    client_profile = ClientProfileSerializer(read_only=True)
    verification_status = serializers.SerializerMethodField()
    factory_id = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id", "name", "email", "phone", "role", "company_name", "address", "city", "state", "country",
            "is_active", "is_demo", "created_at", "client_profile", "verification_status", "factory_id",
        )
        read_only_fields = fields

    def _profile(self, obj):
        return getattr(obj, "factory_profile", None) if obj.role == Role.FACTORY else None

    def get_verification_status(self, obj):
        profile = self._profile(obj)
        return profile.verification_status if profile else None

    def get_factory_id(self, obj):
        profile = self._profile(obj)
        return profile.id if profile else None


class ProfileUpdateSerializer(serializers.ModelSerializer):
    gst_number = serializers.CharField(max_length=20, required=False, allow_blank=True)
    industry = serializers.CharField(max_length=100, required=False, allow_blank=True)

    class Meta:
        model = User
        fields = ("name", "phone", "company_name", "address", "city", "state", "country", "gst_number", "industry")

    def validate_phone(self, value):
        return validate_phone_value(value)

    def update(self, instance, validated):
        gst = validated.pop("gst_number", None)
        industry = validated.pop("industry", None)
        instance = super().update(instance, validated)
        if instance.role == Role.CLIENT:
            profile, _ = ClientProfile.objects.get_or_create(user=instance)
            if gst is not None:
                profile.gst_number = gst
            if industry is not None:
                profile.industry = industry
            profile.save()
        return instance


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(trim_whitespace=False)
    new_password = serializers.CharField(trim_whitespace=False)

    def validate_old_password(self, value):
        if not self.context["request"].user.check_password(value):
            raise serializers.ValidationError("Your current password is incorrect.")
        return value

    def validate_new_password(self, value):
        errors = _password_errors(value, self.context["request"].user)
        if errors:
            raise serializers.ValidationError(errors)
        return value


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(trim_whitespace=False)


class AdminUserSerializer(UserSerializer):
    class Meta(UserSerializer.Meta):
        fields = ("id", "name", "email", "phone", "role", "company_name", "city", "state", "is_active", "is_demo",
                  "created_at", "verification_status")
        read_only_fields = fields
