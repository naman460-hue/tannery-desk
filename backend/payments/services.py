from django.db import transaction
from django.utils import timezone

from core.activity import log_activity
from notifications.services import notify, notify_admins
from orders.models import Order

from .models import Payment


@transaction.atomic
def mark_paid(payment_id, razorpay_payment_id, signature=""):
    """Idempotent: safe to call from both the browser callback and the webhook."""
    payment = Payment.objects.select_for_update().get(pk=payment_id)
    if payment.status == Payment.Status.PAID:
        return payment
    payment.status = Payment.Status.PAID
    payment.razorpay_payment_id = razorpay_payment_id
    payment.razorpay_signature = signature
    payment.failure_reason = ""
    payment.paid_at = timezone.now()
    payment.save()

    order = Order.objects.select_for_update().select_related("factory__user", "client").get(pk=payment.order_id)
    if payment.purpose == Payment.Purpose.ADVANCE:
        order.payment_status = (Order.PaymentStatus.PAID if order.remaining_amount <= 0
                                else Order.PaymentStatus.ADVANCE_PAID)
        if order.status == Order.Status.ORDER_CREATED:
            order.status = Order.Status.PAYMENT_RECEIVED
    else:
        order.payment_status = Order.PaymentStatus.PAID
    order.save()

    link = f"#/orders/{order.pk}"
    label = payment.get_purpose_display().lower()
    notify(order.client, "Payment successful", f"We received your {label} of ₹{payment.amount:,.2f} for {order.number}.",
           "PAYMENT", link)
    notify(order.factory.user, "Payment received", f"The client paid the {label} for {order.number}."
           + (" You can start production." if payment.purpose == Payment.Purpose.ADVANCE else ""), "PAYMENT", link)
    notify_admins("Payment received", f"₹{payment.amount:,.2f} ({label}) for {order.number}.", "PAYMENT", link)
    log_activity(payment.payer, f"Paid ₹{payment.amount:,.2f} ({label}) for {order.number}")
    return payment


@transaction.atomic
def mark_failed(payment_id, reason=""):
    payment = Payment.objects.select_for_update().select_related("order").get(pk=payment_id)
    if payment.status != Payment.Status.CREATED:
        return payment
    payment.status = Payment.Status.FAILED
    payment.failure_reason = (reason or "Payment was not completed.")[:300]
    payment.save(update_fields=["status", "failure_reason"])
    notify(payment.payer, "Payment failed", f"Your payment for {payment.order.number} did not go through. "
           "Nothing was charged. Please try again.", "PAYMENT", f"#/orders/{payment.order_id}")
    return payment
