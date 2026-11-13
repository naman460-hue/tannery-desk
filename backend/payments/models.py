from django.conf import settings
from django.db import models

from orders.models import Order


class Payment(models.Model):
    class Purpose(models.TextChoices):
        ADVANCE = "ADVANCE", "Advance payment"
        REMAINING = "REMAINING", "Remaining payment"

    class Status(models.TextChoices):
        CREATED = "CREATED", "Waiting for payment"
        PAID = "PAID", "Paid"
        FAILED = "FAILED", "Failed"

    class Mode(models.TextChoices):
        SANDBOX = "SANDBOX", "Sandbox (test, no real money)"
        RAZORPAY = "RAZORPAY", "Razorpay"

    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="payments")
    payer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="payments")
    purpose = models.CharField(max_length=10, choices=Purpose.choices)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3, default="INR")
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.CREATED, db_index=True)
    mode = models.CharField(max_length=10, choices=Mode.choices, default=Mode.RAZORPAY)
    razorpay_order_id = models.CharField(max_length=60, unique=True)
    razorpay_payment_id = models.CharField(max_length=60, blank=True)
    razorpay_signature = models.CharField(max_length=200, blank=True)
    failure_reason = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"Payment {self.pk} ({self.status})"

    @property
    def receipt_number(self):
        return f"TD-RCPT-{self.pk:06d}"
