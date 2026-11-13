from django.db import models

from common.storage import RandomPath
from factories.models import FactoryProfile


class LeatherProduct(models.Model):
    factory = models.ForeignKey(FactoryProfile, on_delete=models.CASCADE, related_name="products")
    name = models.CharField(max_length=200)
    leather_type = models.CharField(max_length=40, db_index=True)
    finish = models.CharField(max_length=40, db_index=True)
    application = models.CharField(max_length=40, db_index=True)
    color = models.CharField(max_length=40, db_index=True)
    thickness_min = models.DecimalField(max_digits=4, decimal_places=2)
    thickness_max = models.DecimalField(max_digits=4, decimal_places=2)
    moq = models.DecimalField("Minimum order quantity", max_digits=12, decimal_places=2)
    unit = models.CharField(max_length=10, default="SQ_FT")
    lead_time_days = models.PositiveIntegerField()
    certifications = models.CharField(max_length=300, blank=True, help_text="Comma-separated, e.g. LWG Gold, REACH")
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to=RandomPath("products"), blank=True, null=True)
    sample_available = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name

    @property
    def certification_list(self):
        return [c.strip() for c in self.certifications.split(",") if c.strip()]
