from django.conf import settings
from django.db import models

from common.storage import RandomPath, private_storage
from factories.models import FactoryProfile
from rfqs.models import FactoryQuotation, RFQ


class Order(models.Model):
    class Status(models.TextChoices):
        ORDER_CREATED = "ORDER_CREATED", "Order Created"
        PAYMENT_RECEIVED = "PAYMENT_RECEIVED", "Payment Received"
        PRODUCTION_STARTED = "PRODUCTION_STARTED", "Production Started"
        QUALITY_CHECK = "QUALITY_CHECK", "Quality Check"
        PACKAGING = "PACKAGING", "Packaging"
        DISPATCHED = "DISPATCHED", "Dispatched"
        IN_TRANSIT = "IN_TRANSIT", "In Transit"
        DELIVERED = "DELIVERED", "Delivered"
        COMPLETED = "COMPLETED", "Completed"
        CANCELLED = "CANCELLED", "Cancelled"

    class PaymentStatus(models.TextChoices):
        PENDING = "PENDING", "Advance payment due"
        ADVANCE_PAID = "ADVANCE_PAID", "Advance paid"
        PAID = "PAID", "Fully paid"

    number = models.CharField(max_length=20, unique=True, null=True, blank=True)
    client = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="orders")
    factory = models.ForeignKey(FactoryProfile, on_delete=models.PROTECT, related_name="orders")
    rfq = models.OneToOneField(RFQ, on_delete=models.PROTECT, related_name="order")
    quotation = models.OneToOneField(FactoryQuotation, on_delete=models.PROTECT, related_name="order")
    total_amount = models.DecimalField(max_digits=14, decimal_places=2)
    advance_amount = models.DecimalField(max_digits=14, decimal_places=2)
    remaining_amount = models.DecimalField(max_digits=14, decimal_places=2)
    payment_status = models.CharField(max_length=14, choices=PaymentStatus.choices, default=PaymentStatus.PENDING)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ORDER_CREATED, db_index=True)
    progress_percent = models.PositiveSmallIntegerField(default=0)
    expected_completion = models.DateField(null=True, blank=True)
    expected_delivery = models.DateField(null=True, blank=True)
    ready_for_dispatch = models.BooleanField(default=False)
    courier_name = models.CharField(max_length=100, blank=True)
    tracking_number = models.CharField(max_length=100, blank=True)
    dispatched_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return self.number or f"Order #{self.pk}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.number:
            self.number = f"ORD-{2000 + self.pk}"
            super().save(update_fields=["number"])


# The order lifecycle after the client approves a quotation (everything except CANCELLED, in order)
STAGE_ORDER = [s.value for s in Order.Status if s != Order.Status.CANCELLED]


class ProductionUpdate(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="updates")
    stage = models.CharField(max_length=20, choices=Order.Status.choices)
    percentage = models.PositiveSmallIntegerField(default=0)
    message = models.CharField(max_length=500, blank=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]


class OrderDocument(models.Model):
    class Kind(models.TextChoices):
        QC_REPORT = "QC_REPORT", "Quality check report"
        PACKING_LIST = "PACKING_LIST", "Packing list"
        INVOICE = "INVOICE", "Invoice"
        OTHER = "OTHER", "Other"

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="documents")
    kind = models.CharField(max_length=14, choices=Kind.choices, default=Kind.OTHER)
    title = models.CharField(max_length=150)
    file = models.FileField(upload_to=RandomPath("order-docs"), storage=private_storage)
    original_name = models.CharField(max_length=150)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class Dispute(models.Model):
    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        UNDER_REVIEW = "UNDER_REVIEW", "Under review"
        RESOLVED = "RESOLVED", "Resolved"
        CLOSED = "CLOSED", "Closed"

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="disputes")
    raised_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="disputes")
    subject = models.CharField(max_length=150)
    description = models.TextField(max_length=2000)
    status = models.CharField(max_length=14, choices=Status.choices, default=Status.OPEN, db_index=True)
    resolution = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
