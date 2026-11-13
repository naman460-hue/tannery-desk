import json

from django.conf import settings
from django.db import transaction
from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from common.permissions import IsClient
from orders.models import Order
from orders.services import next_payment

from . import gateway
from .models import Payment
from .serializers import PaymentSerializer
from .services import mark_failed, mark_paid


def payments_for(user):
    qs = Payment.objects.select_related("order", "payer")
    if user.role == "CLIENT":
        return qs.filter(order__client=user)
    if user.role == "FACTORY":
        return qs.filter(order__factory=user.factory_profile, status=Payment.Status.PAID)
    return qs


class PaymentListView(ListAPIView):
    serializer_class = PaymentSerializer

    def get_queryset(self):
        qs = payments_for(self.request.user)
        params = self.request.query_params
        if params.get("order", "").isdigit():
            qs = qs.filter(order_id=int(params["order"]))
        if params.get("status") in Payment.Status.values:
            qs = qs.filter(status=params["status"])
        return qs


class PaymentDetailView(RetrieveAPIView):
    serializer_class = PaymentSerializer

    def get_queryset(self):
        return payments_for(self.request.user)


class CreatePaymentView(APIView):
    """Client starts a payment. The amount is decided here on the server, never by the browser."""

    permission_classes = [IsClient]
    throttle_scope = "payment"

    def post(self, request):
        order = Order.objects.filter(pk=request.data.get("order_id"), client=request.user).first()
        if not order:
            raise ValidationError({"order_id": ["We couldn't find that order."]})
        due = next_payment(order)
        purpose = request.data.get("purpose")
        if not due or due["purpose"] != purpose:
            raise ValidationError({"detail": ["There is no payment due on this order right now."]})
        with transaction.atomic():
            Order.objects.select_for_update().get(pk=order.pk)
            payment = Payment.objects.filter(order=order, purpose=purpose, status=Payment.Status.CREATED).first()
            if not payment:
                try:
                    gw_id = gateway.create_gateway_order(due["amount"], f"{order.number}-{purpose}",
                                                         {"order": order.number, "purpose": purpose})
                except gateway.GatewayError as exc:
                    return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
                payment = Payment.objects.create(
                    order=order, payer=request.user, purpose=purpose, amount=due["amount"],
                    mode=Payment.Mode.SANDBOX if gateway.is_sandbox() else Payment.Mode.RAZORPAY,
                    razorpay_order_id=gw_id)
        return Response({
            "payment_id": payment.pk,
            "razorpay_order_id": payment.razorpay_order_id,
            "amount_paise": gateway.to_paise(payment.amount),
            "amount": str(payment.amount),
            "currency": payment.currency,
            "key_id": "" if gateway.is_sandbox() else settings.RAZORPAY_KEY_ID,
            "sandbox": gateway.is_sandbox(),
            "description": f"{order.number} - {payment.get_purpose_display()}",
            "client_name": request.user.name,
            "client_email": request.user.email,
        }, status=status.HTTP_201_CREATED)


class VerifyPaymentView(APIView):
    """Success is decided here by checking the gateway signature. The browser saying 'paid' is not enough."""

    permission_classes = [IsClient]
    throttle_scope = "payment"

    def post(self, request):
        data = request.data
        payment = payments_for(request.user).filter(razorpay_order_id=data.get("razorpay_order_id")).first()
        if not payment:
            raise ValidationError({"detail": ["We couldn't find that payment."]})
        if not gateway.signature_is_valid(payment.razorpay_order_id, data.get("razorpay_payment_id"),
                                          data.get("razorpay_signature")):
            mark_failed(payment.pk, "Payment could not be verified.")
            raise ValidationError({"detail": ["Payment failed. We could not verify it, so nothing has been marked as paid."]})
        payment = mark_paid(payment.pk, data["razorpay_payment_id"], data["razorpay_signature"])
        return Response(PaymentSerializer(payment).data)


class ReportFailureView(APIView):
    """The browser reports a cancelled or declined checkout. This can only mark an unpaid attempt as failed."""

    permission_classes = [IsClient]

    def post(self, request):
        payment = payments_for(request.user).filter(razorpay_order_id=request.data.get("razorpay_order_id")).first()
        if not payment:
            raise ValidationError({"detail": ["We couldn't find that payment."]})
        payment = mark_failed(payment.pk, str(request.data.get("reason") or "")[:300])
        return Response(PaymentSerializer(payment).data)


class SandboxPayView(APIView):
    """Development-only stand-in for the Razorpay checkout."""

    permission_classes = [IsClient]

    def post(self, request, pk):
        if (not settings.DEBUG and not settings.TESTING) or not gateway.is_sandbox():
            raise NotFound()
        payment = payments_for(request.user).filter(pk=pk, status=Payment.Status.CREATED).first()
        if not payment:
            raise ValidationError({"detail": ["There is no pending payment to complete."]})
        if request.data.get("outcome") == "fail":
            return Response(PaymentSerializer(mark_failed(payment.pk, "Sandbox: payment declined.")).data)
        fake_payment_id = "pay_sandbox_" + payment.razorpay_order_id[-8:]
        signature = gateway.sign(payment.razorpay_order_id, fake_payment_id)
        # goes through exactly the same verification as a real payment
        if not gateway.signature_is_valid(payment.razorpay_order_id, fake_payment_id, signature):
            raise ValidationError({"detail": ["Payment failed."]})
        return Response(PaymentSerializer(mark_paid(payment.pk, fake_payment_id, signature)).data)


class RazorpayWebhookView(APIView):
    """Razorpay calls this server-to-server, so payments are recorded even if the browser is closed."""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = []

    def post(self, request):
        raw = request.body
        if not settings.RAZORPAY_WEBHOOK_SECRET:
            return Response({"detail": "Webhook is not configured."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        if not gateway.webhook_signature_is_valid(raw, request.headers.get("X-Razorpay-Signature", "")):
            return Response({"detail": "Invalid signature."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            event = json.loads(raw)
            entity = event["payload"]["payment"]["entity"]
            payment = Payment.objects.filter(razorpay_order_id=entity["order_id"]).first()
        except (ValueError, KeyError, TypeError):
            return Response({"detail": "Unreadable event."}, status=status.HTTP_400_BAD_REQUEST)
        if payment:
            if event.get("event") in ("payment.captured", "order.paid"):
                mark_paid(payment.pk, entity.get("id", ""), "webhook")
            elif event.get("event") == "payment.failed":
                mark_failed(payment.pk, (entity.get("error_description") or "")[:300])
        return Response({"status": "ok"})
