from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from common.files import file_response
from common.permissions import IsAdminRole, IsClient, IsFactory
from core.activity import log_activity
from notifications.services import notify, notify_admins

from .models import STAGE_ORDER, Dispute, Order, OrderDocument, ProductionUpdate
from .serializers import (
    DeliveryDateSerializer, DispatchInputSerializer, DisputeSerializer, OrderDetailSerializer, OrderDocumentSerializer,
    OrderSerializer, ProductionInputSerializer,
)

CLOSED = [Order.Status.COMPLETED, Order.Status.CANCELLED]
PRODUCTION_BUCKET = [Order.Status.PRODUCTION_STARTED, Order.Status.QUALITY_CHECK, Order.Status.PACKAGING]


def orders_for(user):
    qs = Order.objects.select_related("client", "factory", "rfq", "quotation")
    if user.role == "CLIENT":
        return qs.filter(client=user)
    if user.role == "FACTORY":
        return qs.filter(factory=user.factory_profile)
    return qs


def idx(status_value):
    return STAGE_ORDER.index(status_value)


class OrderViewSet(viewsets.ReadOnlyModelViewSet):
    throttle_scope = None

    def get_serializer_class(self):
        return OrderDetailSerializer if self.action == "retrieve" else OrderSerializer

    def get_permissions(self):
        if self.action in ("production", "ready_for_dispatch", "dispatch_order", "expected_delivery"):
            return [IsFactory()]
        if self.action == "confirm_delivery":
            return [IsClient()]
        return [IsAuthenticated()]

    def get_queryset(self):
        qs = orders_for(self.request.user)
        params = self.request.query_params
        bucket = params.get("bucket")
        if bucket == "active":
            qs = qs.exclude(status__in=CLOSED)
        elif bucket == "production":
            qs = qs.filter(status__in=PRODUCTION_BUCKET)
        elif bucket == "completed":
            qs = qs.filter(status=Order.Status.COMPLETED)
        if params.get("status") in Order.Status.values:
            qs = qs.filter(status=params["status"])
        q = (params.get("q") or "").strip()
        if q:
            qs = qs.filter(Q(number__icontains=q) | Q(rfq__number__icontains=q) | Q(factory__name__icontains=q)
                           | Q(client__company_name__icontains=q) | Q(client__name__icontains=q))
        return qs

    def _detail(self, order):
        order = self.get_queryset().get(pk=order.pk)
        return Response(OrderDetailSerializer(order, context={"request": self.request}).data)

    # ---- factory actions ---------------------------------------------------------------------
    @action(detail=True, methods=["post"])
    def production(self, request, pk=None):
        serializer = ProductionInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        with transaction.atomic():
            order = Order.objects.select_for_update().get(pk=self.get_object().pk)
            if order.status in CLOSED:
                raise ValidationError({"detail": ["This order is closed."]})
            if idx(order.status) < idx(Order.Status.PAYMENT_RECEIVED):
                raise ValidationError({"detail": ["Production can start once the client has paid the advance."]})
            new_stage = data["stage"]
            if idx(new_stage) < idx(order.status):
                raise ValidationError({"stage": ["An order cannot go back to an earlier stage."]})
            dispatched = idx(order.status) >= idx(Order.Status.DISPATCHED)
            if new_stage in ("IN_TRANSIT", "DELIVERED") and not dispatched:
                raise ValidationError({"stage": ["Please dispatch the order first."]})
            if new_stage not in ("IN_TRANSIT", "DELIVERED") and dispatched:
                raise ValidationError({"stage": ["This order has already been dispatched."]})
            percentage = 100 if new_stage in ("IN_TRANSIT", "DELIVERED") else data["percentage"]
            if percentage < order.progress_percent:
                raise ValidationError({"percentage": ["Progress cannot go down."]})
            order.status = new_stage
            order.progress_percent = percentage
            if new_stage == "DELIVERED":
                order.delivered_at = timezone.now()
            order.save()
            update = ProductionUpdate.objects.create(order=order, stage=new_stage, percentage=percentage,
                                                     message=data.get("message", ""), updated_by=request.user)
        label = update.get_stage_display()
        notify(order.client, f"Order update: {label}", f"{order.number} is now at '{label}' ({percentage}%)."
               + (" Please confirm once you have checked the goods." if new_stage == "DELIVERED" else ""),
               "PRODUCTION", f"#/orders/{order.pk}")
        return self._detail(order)

    @action(detail=True, methods=["post"], url_path="ready-for-dispatch")
    def ready_for_dispatch(self, request, pk=None):
        order = self.get_object()
        if order.status != Order.Status.PACKAGING:
            raise ValidationError({"detail": ["The order must be at the Packaging stage first."]})
        order.ready_for_dispatch = True
        order.save(update_fields=["ready_for_dispatch", "updated_at"])
        notify(order.client, "Order ready for dispatch", f"{order.number} is packed and ready to leave the factory.",
               "ORDER", f"#/orders/{order.pk}")
        return self._detail(order)

    @action(detail=True, methods=["post"], url_path="dispatch")
    def dispatch_order(self, request, pk=None):
        serializer = DispatchInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        with transaction.atomic():
            order = Order.objects.select_for_update().get(pk=self.get_object().pk)
            if order.status != Order.Status.PACKAGING or not order.ready_for_dispatch:
                raise ValidationError({"detail": ["Please mark the order as ready for dispatch first."]})
            order.status = Order.Status.DISPATCHED
            order.courier_name = data["courier_name"]
            order.tracking_number = data["tracking_number"]
            order.dispatched_at = timezone.now()
            order.progress_percent = 100
            if data.get("expected_delivery"):
                order.expected_delivery = data["expected_delivery"]
            order.save()
            ProductionUpdate.objects.create(
                order=order, stage=Order.Status.DISPATCHED, percentage=100, updated_by=request.user,
                message=f"Dispatched with {order.courier_name}, tracking {order.tracking_number}.")
        notify(order.client, "Order dispatched", f"{order.number} was dispatched with {order.courier_name}. "
               f"Tracking: {order.tracking_number}.", "ORDER", f"#/orders/{order.pk}")
        return self._detail(order)

    @action(detail=True, methods=["post"], url_path="expected-delivery")
    def expected_delivery(self, request, pk=None):
        serializer = DeliveryDateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order = self.get_object()
        if order.status in (Order.Status.DELIVERED, *CLOSED):
            raise ValidationError({"detail": ["This order is already delivered or closed."]})
        order.expected_delivery = serializer.validated_data["expected_delivery"]
        order.save(update_fields=["expected_delivery", "updated_at"])
        note = serializer.validated_data.get("message", "")
        notify(order.client, "Expected delivery changed",
               f"{order.number} is now expected on {order.expected_delivery:%d %b %Y}." + (f" {note}" if note else ""),
               "ORDER", f"#/orders/{order.pk}")
        return self._detail(order)

    # ---- client action -------------------------------------------------------------------------
    @action(detail=True, methods=["post"], url_path="confirm-delivery")
    def confirm_delivery(self, request, pk=None):
        order = self.get_object()
        if order.status != Order.Status.DELIVERED:
            raise ValidationError({"detail": ["You can confirm once the order has been delivered."]})
        if order.payment_status != Order.PaymentStatus.PAID:
            raise ValidationError({"detail": ["Please pay the remaining amount before completing the order."]})
        order.status = Order.Status.COMPLETED
        order.save(update_fields=["status", "updated_at"])
        ProductionUpdate.objects.create(order=order, stage=Order.Status.COMPLETED, percentage=100,
                                        message="Delivery confirmed by the client.", updated_by=request.user)
        notify(order.factory.user, "Order completed", f"{order.number} was confirmed as delivered.", "ORDER",
               f"#/orders/{order.pk}")
        notify(order.client, "Order completed", f"Thank you. Please rate {order.factory.name}.", "ORDER",
               f"#/orders/{order.pk}")
        log_activity(request.user, f"Completed {order.number}")
        return self._detail(order)

    # ---- documents -------------------------------------------------------------------------------
    @action(detail=True, methods=["get", "post"], parser_classes=[MultiPartParser, FormParser], throttle_scope="upload")
    def documents(self, request, pk=None):
        order = self.get_object()
        if request.method == "GET":
            return Response(OrderDocumentSerializer(order.documents.all(), many=True).data)
        if request.user.role not in ("FACTORY", "ADMIN"):
            raise ValidationError({"detail": ["Only the factory can upload order documents."]})
        serializer = OrderDocumentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(order=order, uploaded_by=request.user)
        if request.user.role == "FACTORY":
            notify(order.client, "New document added", f"{order.number}: {serializer.instance.title}.", "ORDER",
                   f"#/orders/{order.pk}")
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class OrderDocumentDownloadView(APIView):
    def get(self, request, pk):
        doc = OrderDocument.objects.filter(pk=pk).first()
        if not doc or not orders_for(request.user).filter(pk=doc.order_id).exists():
            raise NotFound()
        return file_response(doc.file, doc.original_name)


class DisputeViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = DisputeSerializer

    def get_permissions(self):
        return [IsAdminRole()] if self.action == "partial_update" else [IsAuthenticated()]

    def get_queryset(self):
        qs = Dispute.objects.select_related("order", "raised_by")
        user = self.request.user
        if user.role != "ADMIN":
            qs = qs.filter(order__in=orders_for(user))
        if self.request.query_params.get("status") in Dispute.Status.values:
            qs = qs.filter(status=self.request.query_params["status"])
        return qs

    def create(self, request):
        if request.user.role not in ("CLIENT", "FACTORY"):
            raise ValidationError({"detail": ["Only the client or factory on an order can raise a dispute."]})
        order = orders_for(request.user).filter(pk=request.data.get("order")).first()
        if not order:
            raise ValidationError({"order": ["Please choose one of your orders."]})
        serializer = DisputeSerializer(data={"subject": request.data.get("subject"),
                                             "description": request.data.get("description"), "order": order.pk})
        serializer.is_valid(raise_exception=True)
        subject = serializer.validated_data["subject"].strip()
        description = serializer.validated_data["description"].strip()
        if not subject or not description:
            raise ValidationError({"description": ["Please describe the problem."]})
        dispute = Dispute.objects.create(order=order, raised_by=request.user, subject=subject, description=description)
        notify_admins("New dispute", f"{order.number}: {subject}", "ORDER", f"#/orders/{order.pk}")
        log_activity(request.user, f"Raised a dispute on {order.number}")
        return Response(DisputeSerializer(dispute).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None):
        dispute = self.get_object()
        new_status = request.data.get("status", dispute.status)
        if new_status not in Dispute.Status.values:
            raise ValidationError({"status": ["Please select a valid status."]})
        resolution = (request.data.get("resolution", dispute.resolution) or "").strip()[:2000]
        if new_status in ("RESOLVED", "CLOSED") and not resolution:
            raise ValidationError({"resolution": ["Please add a short note on how this was resolved."]})
        dispute.status, dispute.resolution = new_status, resolution
        dispute.save()
        notify(dispute.raised_by, "Dispute updated",
               f"Your dispute on {dispute.order.number} is now '{dispute.get_status_display()}'.", "ORDER",
               f"#/orders/{dispute.order_id}")
        log_activity(request.user, f"Dispute #{dispute.pk} set to {new_status}")
        return Response(DisputeSerializer(dispute).data)
