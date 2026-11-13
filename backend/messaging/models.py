from django.conf import settings
from django.db import models

from common.storage import RandomPath, private_storage
from orders.models import Order
from rfqs.models import RFQ


class Message(models.Model):
    """A message in the conversation between one client and one factory, tied to an RFQ or to an order."""

    client = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    factory = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    rfq = models.ForeignKey(RFQ, null=True, blank=True, on_delete=models.CASCADE, related_name="messages")
    order = models.ForeignKey(Order, null=True, blank=True, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sent_messages")
    body = models.TextField(max_length=2000, blank=True)
    attachment = models.FileField(upload_to=RandomPath("message-files"), storage=private_storage, null=True, blank=True)
    attachment_name = models.CharField(max_length=150, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [models.Index(fields=["rfq", "client", "factory"]), models.Index(fields=["order"])]
