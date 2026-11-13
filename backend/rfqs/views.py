from django.db import IntegrityError, transaction
from django.db.models import Q
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from common.files import file_response
from common.permissions import IsAdminRole, IsClient, IsFactory, IsVerifiedFactory
from common.validators import clean_filename
from core.activity import log_activity
from factories.models import FactoryProfile
from notifications.services import notify
from orders.services import accept_quotation

from .matching import recommendation_score, score_factory
from .models import FactoryQuotation, RFQ, RFQAttachment, RFQMatch
from .serializers import AttachmentUploadSerializer, QuotationSerializer, RFQSerializer
from .services import submit_rfq

MAX_ATTACHMENTS = 5
OPEN = [RFQ.Status.SUBMITTED, RFQ.Status.MATCHING, RFQ.Status.QUOTATION_RECEIVED]


def rfq_queryset_for(user):
    qs = RFQ.objects.select_related("client").prefetch_related("attachments", "matches__factory")
    if user.role == "CLIENT":
        return qs.filter(client=user)
    if user.role == "FACTORY":
        return qs.filter(matches__factory=user.factory_profile)
    return qs


class RFQViewSet(viewsets.ModelViewSet):
    serializer_class = RFQSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]
    throttle_scope = None

    def get_permissions(self):
        if self.action in ("create", "partial_update", "attachments"):
            return [IsClient()]
        if self.action == "respond":
            return [IsFactory()]
        if self.action == "assign":
            return [IsAdminRole()]
        return [IsAuthenticated()]

    def get_queryset(self):
        user = self.request.user
        qs = rfq_queryset_for(user)
        params = self.request.query_params
        if params.get("status") in RFQ.Status.values:
            qs = qs.filter(status=params["status"])
        if params.get("open") == "1":
            qs = qs.filter(status__in=OPEN)
        if user.role == "FACTORY" and params.get("response") in RFQMatch.Response.values:
            qs = qs.filter(matches__factory=user.factory_profile, matches__response=params["response"])
        q = (params.get("q") or "").strip()
        if q:
            qs = qs.filter(Q(number__icontains=q) | Q(leather_type__icontains=q) | Q(application__icontains=q)
                           | Q(color__icontains=q) | Q(finish__icontains=q))
        return qs.distinct()

    def _ctx(self):
        return {"request": self.request}

    def _fresh(self, rfq, code=status.HTTP_200_OK):
        rfq = self.get_queryset().get(pk=rfq.pk)
        return Response(RFQSerializer(rfq, context=self._ctx()).data, status=code)

    def create(self, request, *args, **kwargs):
        serializer = RFQSerializer(data=request.data, context=self._ctx())
        serializer.is_valid(raise_exception=True)
        token = serializer.validated_data.get("client_token", "")
        if token:
            existing = RFQ.objects.filter(client=request.user, client_token=token).first()
            if existing:
                return Response(RFQSerializer(existing, context=self._ctx()).data, status=status.HTTP_200_OK)
        try:
            with transaction.atomic():
                rfq = serializer.save(client=request.user)
        except IntegrityError:
            existing = RFQ.objects.filter(client=request.user, client_token=token).first()
            if existing:
                return Response(RFQSerializer(existing, context=self._ctx()).data, status=status.HTTP_200_OK)
            raise
        submit_rfq(rfq)
        return self._fresh(rfq, status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        rfq = self.get_object()
        if rfq.status not in (RFQ.Status.SUBMITTED, RFQ.Status.MATCHING) or \
                rfq.quotations.exclude(status="WITHDRAWN").exists():
            raise ValidationError({"detail": ["This requirement can no longer be edited because quotations have been received."]})
        serializer = RFQSerializer(rfq, data=request.data, partial=True, context=self._ctx())
        serializer.is_valid(raise_exception=True)
        serializer.save()
        submit_rfq(rfq, first_time=False)
        return self._fresh(rfq)

    @action(detail=True, methods=["post"], parser_classes=[MultiPartParser, FormParser], throttle_scope="upload")
    def attachments(self, request, pk=None):
        rfq = self.get_object()
        if rfq.status == RFQ.Status.CANCELLED:
            raise ValidationError({"detail": ["This requirement was cancelled."]})
        if rfq.attachments.count() >= MAX_ATTACHMENTS:
            raise ValidationError({"detail": [f"You can attach up to {MAX_ATTACHMENTS} files."]})
        serializer = AttachmentUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        upload = serializer.validated_data["file"]
        RFQAttachment.objects.create(rfq=rfq, file=upload, original_name=clean_filename(upload.name),
                                     uploaded_by=request.user)
        return self._fresh(rfq, status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        rfq = self.get_object()
        if request.user.role not in ("CLIENT", "ADMIN"):
            raise PermissionDenied()
        if not rfq.is_open:
            raise ValidationError({"detail": ["This requirement can no longer be cancelled."]})
        with transaction.atomic():
            rfq.status = RFQ.Status.CANCELLED
            rfq.save(update_fields=["status", "updated_at"])
            rfq.quotations.filter(status="SUBMITTED").update(status="CLOSED")
        for match in rfq.matches.select_related("factory__user"):
            notify(match.factory.user, "RFQ cancelled", f"{rfq.number} was cancelled by the client.", "RFQ",
                   f"#/rfqs/{rfq.pk}")
        log_activity(request.user, f"Cancelled {rfq.number}")
        return self._fresh(rfq)

    @action(detail=True, methods=["post"])
    def respond(self, request, pk=None):
        rfq = self.get_object()
        match = rfq.matches.get(factory=request.user.factory_profile)
        choice = request.data.get("action")
        if choice not in ("accept", "decline"):
            raise ValidationError({"action": ["Please choose accept or decline."]})
        if not rfq.is_open:
            raise ValidationError({"detail": ["This requirement is closed."]})
        if match.response == RFQMatch.Response.QUOTED:
            raise ValidationError({"detail": ["You have already sent a quotation. Withdraw it first if you want to decline."]})
        if choice == "accept":
            match.response = RFQMatch.Response.ACCEPTED
        else:
            match.response = RFQMatch.Response.DECLINED
            match.decline_reason = (request.data.get("reason") or "")[:300]
        match.save(update_fields=["response", "decline_reason", "updated_at"])
        return self._fresh(rfq)

    @action(detail=True, methods=["post"])
    def assign(self, request, pk=None):
        rfq = self.get_object()
        if not rfq.is_open:
            raise ValidationError({"detail": ["This requirement is closed."]})
        factory = FactoryProfile.objects.marketplace().filter(pk=request.data.get("factory_id")).first()
        if not factory:
            raise ValidationError({"factory_id": ["Please choose a verified factory."]})
        score, reasons = score_factory(rfq, factory)
        _, created = RFQMatch.objects.get_or_create(
            rfq=rfq, factory=factory, defaults={"score": score, "reasons": reasons, "assigned_by_admin": True})
        if not created:
            raise ValidationError({"detail": ["This factory already has the RFQ."]})
        if rfq.status == RFQ.Status.SUBMITTED:
            rfq.status = RFQ.Status.MATCHING
            rfq.save(update_fields=["status", "updated_at"])
        notify(factory.user, "New RFQ available", f"{rfq.number}: {rfq.title} was assigned to you.", "RFQ",
               f"#/rfqs/{rfq.pk}")
        log_activity(request.user, f"Assigned {rfq.number} to {factory.name}")
        return self._fresh(rfq)


class AttachmentDownloadView(APIView):
    def get(self, request, pk):
        att = RFQAttachment.objects.filter(pk=pk).first()
        if not att or not rfq_queryset_for(request.user).filter(pk=att.rfq_id).exists():
            raise NotFound()
        return file_response(att.file, att.original_name)


# ------------------------------------------------------------------------------------------------
# Quotations
# ------------------------------------------------------------------------------------------------
def annotate_recommendations(quotations):
    """Flags the best-value submitted quotation as 'recommended' (see matching.recommendation_score)."""
    live = [q for q in quotations if q.status == FactoryQuotation.Status.SUBMITTED]
    if not live:
        return
    matches = {(m.rfq_id, m.factory_id): m for m in RFQMatch.objects.filter(rfq_id__in={q.rfq_id for q in live})}
    cheapest = min(q.price for q in live)
    best, best_score = None, -1
    for q in live:
        m = matches.get((q.rfq_id, q.factory_id))
        q._match_cache = m
        s = recommendation_score(m.score if m else 0, q.price, cheapest, q.factory.rating)
        if s > best_score:
            best, best_score = q, s
    best._recommended = True


class QuotationViewSet(viewsets.ModelViewSet):
    serializer_class = QuotationSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_permissions(self):
        if self.action in ("create", "partial_update", "withdraw"):
            return [IsVerifiedFactory()]
        if self.action in ("accept", "reject"):
            return [IsClient()]
        return [IsAuthenticated()]

    def get_queryset(self):
        user = self.request.user
        qs = FactoryQuotation.objects.select_related("rfq", "factory")
        if user.role == "CLIENT":
            qs = qs.filter(rfq__client=user).exclude(status=FactoryQuotation.Status.WITHDRAWN)
        elif user.role == "FACTORY":
            qs = qs.filter(factory=user.factory_profile)
        params = self.request.query_params
        if params.get("rfq", "").isdigit():
            qs = qs.filter(rfq_id=int(params["rfq"]))
        if params.get("status") in FactoryQuotation.Status.values:
            qs = qs.filter(status=params["status"])
        return qs

    def paginate_queryset(self, queryset):
        page = super().paginate_queryset(queryset)
        if page is not None and self.request.user.role in ("CLIENT", "ADMIN"):
            annotate_recommendations(page)
        return page

    def create(self, request, *args, **kwargs):
        factory = request.user.factory_profile
        rfq_id = str(request.data.get("rfq", ""))
        # A withdrawn quotation can be sent again; any other existing quotation must be edited instead.
        existing = FactoryQuotation.objects.filter(rfq_id=int(rfq_id), factory=factory).first() if rfq_id.isdigit() else None
        if existing and existing.status != FactoryQuotation.Status.WITHDRAWN:
            raise ValidationError({"detail": ["You have already sent a quotation for this RFQ. Please edit it instead."]})
        serializer = QuotationSerializer(existing, data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        rfq = serializer.validated_data["rfq"]
        match = RFQMatch.objects.filter(rfq=rfq, factory=factory).first()
        if not match or match.response == RFQMatch.Response.DECLINED:
            raise ValidationError({"detail": ["This requirement was not sent to your factory."]})
        if not rfq.is_open:
            raise ValidationError({"detail": ["This requirement is closed for new quotations."]})
        with transaction.atomic():
            quotation = serializer.save(factory=factory, price_unit=rfq.unit, status=FactoryQuotation.Status.SUBMITTED)
            match.response = RFQMatch.Response.QUOTED
            match.save(update_fields=["response", "updated_at"])
            if rfq.status in (RFQ.Status.SUBMITTED, RFQ.Status.MATCHING):
                rfq.status = RFQ.Status.QUOTATION_RECEIVED
                rfq.save(update_fields=["status", "updated_at"])
        notify(rfq.client, "New quotation received", f"{factory.name} quoted {rfq.number}.", "QUOTATION",
               f"#/rfqs/{rfq.pk}")
        log_activity(request.user, f"{factory.name} quoted {rfq.number}")
        return Response(QuotationSerializer(quotation, context={"request": request}).data,
                        status=status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        quotation = self.get_object()
        if quotation.status != FactoryQuotation.Status.SUBMITTED or not quotation.rfq.is_open:
            raise ValidationError({"detail": ["This quotation can no longer be changed."]})
        serializer = QuotationSerializer(quotation, data=request.data, partial=True, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        notify(quotation.rfq.client, "Quotation updated",
               f"{quotation.factory.name} updated its quotation for {quotation.rfq.number}.", "QUOTATION",
               f"#/rfqs/{quotation.rfq_id}")
        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    def withdraw(self, request, pk=None):
        quotation = self.get_object()
        if quotation.status != FactoryQuotation.Status.SUBMITTED:
            raise ValidationError({"detail": ["This quotation can no longer be withdrawn."]})
        with transaction.atomic():
            quotation.status = FactoryQuotation.Status.WITHDRAWN
            quotation.save(update_fields=["status", "updated_at"])
            RFQMatch.objects.filter(rfq=quotation.rfq, factory=quotation.factory).update(
                response=RFQMatch.Response.ACCEPTED)
            rfq = quotation.rfq
            if rfq.status == RFQ.Status.QUOTATION_RECEIVED and not rfq.quotations.filter(status="SUBMITTED").exists():
                rfq.status = RFQ.Status.MATCHING
                rfq.save(update_fields=["status", "updated_at"])
        return Response(QuotationSerializer(quotation, context={"request": request}).data)

    @action(detail=True, methods=["post"])
    def accept(self, request, pk=None):
        quotation = self.get_object()
        order = accept_quotation(quotation.pk, request.user)
        return Response({"detail": "Quotation accepted. Your order has been created.", "order_id": order.pk,
                         "order_number": order.number}, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        quotation = self.get_object()
        if quotation.status != FactoryQuotation.Status.SUBMITTED or not quotation.rfq.is_open:
            raise ValidationError({"detail": ["This quotation can no longer be rejected."]})
        quotation.status = FactoryQuotation.Status.REJECTED
        quotation.save(update_fields=["status", "updated_at"])
        notify(quotation.factory.user, "Quotation rejected",
               f"The client did not accept your quotation for {quotation.rfq.number}.", "QUOTATION",
               f"#/rfqs/{quotation.rfq_id}")
        return Response(QuotationSerializer(quotation, context={"request": request}).data)

    @action(detail=True, methods=["get"], url_path="attachment")
    def attachment(self, request, pk=None):
        quotation = self.get_object()
        return file_response(quotation.attachment, quotation.attachment_name)
