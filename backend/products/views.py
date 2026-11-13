from django.db.models import Q
from rest_framework import generics, viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from common.permissions import IsAdminRole, IsFactory
from common.utils import parse_decimal

from .models import LeatherProduct
from .serializers import ProductSerializer


def filter_products(qs, params):
    for key in ("leather_type", "application", "finish", "color"):
        if params.get(key):
            qs = qs.filter(**{f"{key}__iexact": params[key]})
    lo = parse_decimal(params.get("thickness_min"), "thickness_min")
    hi = parse_decimal(params.get("thickness_max"), "thickness_max")
    if lo is not None:
        qs = qs.filter(thickness_max__gte=lo)
    if hi is not None:
        qs = qs.filter(thickness_min__lte=hi)
    qty = parse_decimal(params.get("moq"), "moq")
    if qty is not None:
        qs = qs.filter(moq__lte=qty)
    loc = (params.get("location") or "").strip()
    if loc:
        qs = qs.filter(Q(factory__city__icontains=loc) | Q(factory__state__icontains=loc))
    cert = (params.get("certification") or "").strip()
    if cert:
        qs = qs.filter(certifications__icontains=cert)
    if params.get("sample") in ("1", "true"):
        qs = qs.filter(sample_available=True)
    q = (params.get("q") or "").strip()
    if q:
        qs = qs.filter(
            Q(name__icontains=q) | Q(leather_type__icontains=q) | Q(application__icontains=q) | Q(finish__icontains=q)
            | Q(color__icontains=q) | Q(factory__name__icontains=q) | Q(factory__city__icontains=q))
    return qs


def marketplace_products():
    return LeatherProduct.objects.filter(
        is_active=True, factory__verification_status="VERIFIED", factory__user__is_active=True).select_related("factory")


class ProductListView(generics.ListAPIView):
    """Public catalog."""

    permission_classes = [AllowAny]
    serializer_class = ProductSerializer

    def get_queryset(self):
        return filter_products(marketplace_products(), self.request.query_params)


class ProductDetailView(generics.RetrieveAPIView):
    permission_classes = [AllowAny]
    serializer_class = ProductSerializer

    def get_queryset(self):
        return marketplace_products()


class MyProductViewSet(viewsets.ModelViewSet):
    """A factory manages its own catalog entries."""

    permission_classes = [IsFactory]
    serializer_class = ProductSerializer
    throttle_scope = "upload"

    def get_queryset(self):
        qs = LeatherProduct.objects.filter(factory=self.request.user.factory_profile).select_related("factory")
        return filter_products(qs, self.request.query_params)

    def perform_create(self, serializer):
        serializer.save(factory=self.request.user.factory_profile)


class AdminProductViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAdminRole]
    serializer_class = ProductSerializer

    def get_queryset(self):
        return filter_products(LeatherProduct.objects.select_related("factory"), self.request.query_params)

    def partial_update(self, request, *args, **kwargs):
        product = self.get_object()
        active = request.data.get("is_active")
        if not isinstance(active, bool):
            raise ValidationError({"is_active": ["Please choose show or hide."]})
        product.is_active = active
        product.save(update_fields=["is_active", "updated_at"])
        return Response(ProductSerializer(product).data)
