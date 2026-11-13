from django.conf import settings
from django.db import models


class Notification(models.Model):
    class Type(models.TextChoices):
        RFQ = "RFQ", "RFQ"
        QUOTATION = "QUOTATION", "Quotation"
        ORDER = "ORDER", "Order"
        PAYMENT = "PAYMENT", "Payment"
        PRODUCTION = "PRODUCTION", "Production"
        FACTORY = "FACTORY", "Factory"
        MESSAGE = "MESSAGE", "Message"
        SYSTEM = "SYSTEM", "System"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    title = models.CharField(max_length=160)
    message = models.CharField(max_length=400)
    type = models.CharField(max_length=12, choices=Type.choices, default=Type.SYSTEM)
    link = models.CharField(max_length=200, blank=True, help_text="Frontend route, e.g. #/orders/5")
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["user", "is_read"])]

    def __str__(self):
        return f"{self.user_id}: {self.title}"
