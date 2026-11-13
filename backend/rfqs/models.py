from django.conf import settings
from django.db import models

from common.storage import RandomPath, private_storage
from factories.models import FactoryProfile
from products.models import LeatherProduct


class RFQ(models.Model):
    class Status(models.TextChoices):
        SUBMITTED = "SUBMITTED", "RFQ Submitted"
        MATCHING = "MATCHING", "Factory Matching"
        QUOTATION_RECEIVED = "QUOTATION_RECEIVED", "Quotation Received"
        ORDER_CREATED = "ORDER_CREATED", "Order Created"
        CANCELLED = "CANCELLED", "Cancelled"

    number = models.CharField(max_length=20, unique=True, null=True, blank=True)
    client = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="rfqs")
    client_token = models.CharField(max_length=64, blank=True, help_text="Stops the same wizard being submitted twice")
    product = models.ForeignKey(LeatherProduct, null=True, blank=True, on_delete=models.SET_NULL, related_name="rfqs")
    need = models.CharField(max_length=40, blank=True)
    leather_type = models.CharField(max_length=40)
    application = models.CharField(max_length=40)
    finish = models.CharField(max_length=40, blank=True)
    color = models.CharField(max_length=40)
    thickness_min = models.DecimalField(max_digits=4, decimal_places=2)
    thickness_max = models.DecimalField(max_digits=4, decimal_places=2)
    quantity = models.DecimalField(max_digits=12, decimal_places=2)
    unit = models.CharField(max_length=10, default="SQ_FT")
    requirements = models.TextField(blank=True)
    target_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    required_date = models.DateField()
    delivery_city = models.CharField(max_length=100, blank=True)
    delivery_state = models.CharField(max_length=100, blank=True)
    required_certifications = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SUBMITTED, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["client", "client_token"], condition=~models.Q(client_token=""),
                                    name="uniq_rfq_client_token")
        ]

    def __str__(self):
        return self.number or f"RFQ #{self.pk}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.number:
            self.number = f"RFQ-{1000 + self.pk}"
            super().save(update_fields=["number"])

    @property
    def title(self):
        return " ".join(p for p in [self.color, self.leather_type, self.finish] if p) + " leather"

    def get_unit_display_label(self):
        from common.choices import unit_label

        return unit_label(self.unit)

    @property
    def is_open(self):
        return self.status in (self.Status.SUBMITTED, self.Status.MATCHING, self.Status.QUOTATION_RECEIVED)


class RFQAttachment(models.Model):
    rfq = models.ForeignKey(RFQ, on_delete=models.CASCADE, related_name="attachments")
    file = models.FileField(upload_to=RandomPath("rfq-files"), storage=private_storage)
    original_name = models.CharField(max_length=150)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]


class RFQMatch(models.Model):
    """One factory that has been sent an RFQ, with the matching score and the factory's response."""

    class Response(models.TextChoices):
        NEW = "NEW", "New"
        ACCEPTED = "ACCEPTED", "Interested"
        DECLINED = "DECLINED", "Declined"
        QUOTED = "QUOTED", "Quoted"

    rfq = models.ForeignKey(RFQ, on_delete=models.CASCADE, related_name="matches")
    factory = models.ForeignKey(FactoryProfile, on_delete=models.CASCADE, related_name="rfq_matches")
    score = models.PositiveSmallIntegerField(default=0)
    reasons = models.JSONField(default=list, blank=True)
    response = models.CharField(max_length=10, choices=Response.choices, default=Response.NEW)
    decline_reason = models.CharField(max_length=300, blank=True)
    assigned_by_admin = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-score", "id"]
        constraints = [models.UniqueConstraint(fields=["rfq", "factory"], name="uniq_rfq_factory_match")]


class FactoryQuotation(models.Model):
    class Status(models.TextChoices):
        SUBMITTED = "SUBMITTED", "Submitted"
        ACCEPTED = "ACCEPTED", "Accepted"
        REJECTED = "REJECTED", "Rejected"
        CLOSED = "CLOSED", "Closed"
        WITHDRAWN = "WITHDRAWN", "Withdrawn"

    rfq = models.ForeignKey(RFQ, on_delete=models.CASCADE, related_name="quotations")
    factory = models.ForeignKey(FactoryProfile, on_delete=models.CASCADE, related_name="quotations")
    price = models.DecimalField("Price per unit", max_digits=12, decimal_places=2)
    price_unit = models.CharField(max_length=10, default="SQ_FT")
    quantity = models.DecimalField(max_digits=12, decimal_places=2)
    moq = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    production_days = models.PositiveIntegerField()
    shipping_days = models.PositiveIntegerField(default=0)
    notes = models.TextField(blank=True)
    validity_date = models.DateField()
    attachment = models.FileField(upload_to=RandomPath("quotation-files"), storage=private_storage, null=True, blank=True)
    attachment_name = models.CharField(max_length=150, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.SUBMITTED, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["price", "id"]
        constraints = [models.UniqueConstraint(fields=["rfq", "factory"], name="uniq_quotation_rfq_factory")]

    def __str__(self):
        return f"Quote {self.pk} for {self.rfq}"

    @property
    def total_amount(self):
        return self.price * self.quantity

    @property
    def lead_time_days(self):
        return self.production_days + self.shipping_days
