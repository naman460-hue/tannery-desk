from django.conf import settings
from django.db import models

from factories.models import FactoryProfile
from orders.models import Order


class Review(models.Model):
    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name="review")
    client = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reviews")
    factory = models.ForeignKey(FactoryProfile, on_delete=models.CASCADE, related_name="reviews")
    rating = models.PositiveSmallIntegerField()
    review = models.TextField(max_length=1500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
