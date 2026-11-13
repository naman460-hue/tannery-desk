from django.db import transaction
from django.db.models import Avg, Count
from rest_framework import serializers, status
from rest_framework.exceptions import ValidationError
from rest_framework.generics import ListAPIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from common.permissions import IsClient
from core.activity import log_activity
from notifications.services import notify
from orders.models import Order

from .models import Review


class ReviewSerializer(serializers.ModelSerializer):
    client_name = serializers.SerializerMethodField()

    class Meta:
        model = Review
        fields = ("id", "order", "factory", "rating", "review", "client_name", "created_at")
        read_only_fields = fields

    def get_client_name(self, obj):
        return obj.client.company_name or obj.client.name


class ReviewListView(ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = ReviewSerializer

    def get_queryset(self):
        qs = Review.objects.select_related("client")
        factory = self.request.query_params.get("factory", "")
        return qs.filter(factory_id=int(factory)) if factory.isdigit() else qs.none()


class ReviewCreateView(APIView):
    permission_classes = [IsClient]

    def post(self, request):
        order = Order.objects.select_related("factory__user").filter(pk=request.data.get("order"),
                                                                     client=request.user).first()
        if not order:
            raise ValidationError({"order": ["Please choose one of your orders."]})
        if order.status != Order.Status.COMPLETED:
            raise ValidationError({"detail": ["You can review a factory once the order is completed."]})
        if Review.objects.filter(order=order).exists():
            raise ValidationError({"detail": ["You have already reviewed this order."]})
        try:
            rating = int(request.data.get("rating"))
        except (TypeError, ValueError):
            rating = 0
        if not 1 <= rating <= 5:
            raise ValidationError({"rating": ["Please select a rating from 1 to 5 stars."]})
        text = (request.data.get("review") or "").strip()
        if len(text) > 1500:
            raise ValidationError({"review": ["Please keep your review under 1500 characters."]})
        with transaction.atomic():
            review = Review.objects.create(order=order, client=request.user, factory=order.factory, rating=rating,
                                           review=text)
            stats = Review.objects.filter(factory=order.factory).aggregate(avg=Avg("rating"), n=Count("id"))
            order.factory.rating = round(stats["avg"], 2)
            order.factory.review_count = stats["n"]
            order.factory.save(update_fields=["rating", "review_count", "updated_at"])
        notify(order.factory.user, "New review", f"{order.number} was rated {rating} out of 5.", "ORDER",
               f"#/orders/{order.pk}")
        log_activity(request.user, f"Reviewed {order.factory.name} ({rating}/5)")
        return Response(ReviewSerializer(review).data, status=status.HTTP_201_CREATED)
