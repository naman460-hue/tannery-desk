from decimal import Decimal

from django.conf import settings
from django.db import models

from common.storage import RandomPath, private_storage


class Verification(models.TextChoices):
    PENDING = "PENDING", "Pending verification"
    VERIFIED = "VERIFIED", "Verified"
    REJECTED = "REJECTED", "Rejected"
    SUSPENDED = "SUSPENDED", "Suspended"


class FactoryQuerySet(models.QuerySet):
    def marketplace(self):
        """Factories that clients may see and that may receive RFQs."""
        return self.filter(verification_status=Verification.VERIFIED, user__is_active=True)


class FactoryProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="factory_profile")
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    address = models.CharField(max_length=300, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, blank=True, default="India")
    contact_name = models.CharField(max_length=150, blank=True)
    contact_phone = models.CharField(max_length=20, blank=True)
    contact_email = models.EmailField(blank=True)
    leather_types = models.JSONField(default=list, blank=True)
    applications = models.JSONField(default=list, blank=True)
    colors = models.JSONField(default=list, blank=True)
    certifications = models.JSONField(default=list, blank=True)
    min_thickness = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    max_thickness = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    min_order_quantity = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    production_capacity = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True,
                                              help_text="Units per month")
    typical_lead_time_days = models.PositiveIntegerField(null=True, blank=True)
    verification_status = models.CharField(max_length=10, choices=Verification.choices,
                                           default=Verification.PENDING, db_index=True)
    verification_note = models.CharField(max_length=300, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    rating = models.DecimalField(max_digits=3, decimal_places=2, default=Decimal("0.00"))
    review_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = FactoryQuerySet.as_manager()

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def is_profile_complete(self):
        return bool(self.leather_types and self.applications and self.city and self.contact_phone
                    and self.min_order_quantity and self.production_capacity and self.typical_lead_time_days)


class FactoryDocument(models.Model):
    class Kind(models.TextChoices):
        CERTIFICATE = "CERTIFICATE", "Certificate"
        SAMPLE = "SAMPLE", "Product sample / image"
        OTHER = "OTHER", "Other"

    factory = models.ForeignKey(FactoryProfile, on_delete=models.CASCADE, related_name="documents")
    kind = models.CharField(max_length=12, choices=Kind.choices, default=Kind.CERTIFICATE)
    title = models.CharField(max_length=150)
    file = models.FileField(upload_to=RandomPath("factory-docs"), storage=private_storage)
    original_name = models.CharField(max_length=150)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return f"{self.factory.name}: {self.title}"
