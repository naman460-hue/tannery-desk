from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from rest_framework.exceptions import ValidationError

from common.utils import money, today
from core.activity import log_activity
from notifications.services import notify, notify_admins
from rfqs.models import FactoryQuotation, RFQ

from .models import STAGE_ORDER, Order


@transaction.atomic
def accept_quotation(quotation_id, client):
    """Client approves a quotation: it becomes ACCEPTED, the rest are closed, and the order is created."""
    quotation = (FactoryQuotation.objects.select_for_update()
                 .select_related("rfq", "factory__user").filter(pk=quotation_id, rfq__client=client).first())
    if not quotation:
        raise ValidationError({"detail": ["We couldn't find that quotation."]})
    rfq = RFQ.objects.select_for_update().get(pk=quotation.rfq_id)
    if not rfq.is_open:
        raise ValidationError({"detail": ["This requirement is no longer open for quotations."]})
    if quotation.status != FactoryQuotation.Status.SUBMITTED:
        raise ValidationError({"detail": ["This quotation can no longer be accepted."]})
    if quotation.validity_date < today():
        raise ValidationError({"detail": ["This quotation has expired. Please ask the factory for a new one."]})
    if quotation.factory.verification_status != "VERIFIED" or not quotation.factory.user.is_active:
        raise ValidationError({"detail": ["This factory is not available right now."]})

    total = money(quotation.price * quotation.quantity)
    advance = money(total * Decimal(settings.ADVANCE_PERCENT) / Decimal(100))
    quotation.status = FactoryQuotation.Status.ACCEPTED
    quotation.save(update_fields=["status", "updated_at"])
    others = list(rfq.quotations.exclude(pk=quotation.pk).filter(status=FactoryQuotation.Status.SUBMITTED)
                  .select_related("factory__user"))
    rfq.quotations.filter(pk__in=[q.pk for q in others]).update(status=FactoryQuotation.Status.CLOSED)
    rfq.status = RFQ.Status.ORDER_CREATED
    rfq.save(update_fields=["status", "updated_at"])

    start = today()
    order = Order.objects.create(
        client=client, factory=quotation.factory, rfq=rfq, quotation=quotation,
        total_amount=total, advance_amount=advance, remaining_amount=total - advance,
        expected_completion=start + timedelta(days=quotation.production_days),
        expected_delivery=start + timedelta(days=quotation.production_days + quotation.shipping_days),
    )
    link = f"#/orders/{order.pk}"
    notify(client, "Quotation accepted", f"Order {order.number} was created. Please pay the advance to start production.",
           "ORDER", link)
    notify(quotation.factory.user, "Your quotation was accepted",
           f"{order.number} for {rfq.number}. Production can start once the client pays the advance.", "ORDER", link)
    for other in others:
        notify(other.factory.user, "Quotation not selected", f"The client chose another factory for {rfq.number}.",
               "QUOTATION", f"#/rfqs/{rfq.pk}")
    notify_admins("New order", f"{order.number} created from {rfq.number}.", "ORDER", link)
    log_activity(client, f"Accepted quotation, created {order.number} with {quotation.factory.name}")
    return order


def next_payment(order):
    """What the client can pay right now, or None."""
    if order.status in (Order.Status.CANCELLED, Order.Status.COMPLETED):
        return None
    if order.payment_status == Order.PaymentStatus.PENDING:
        return {"purpose": "ADVANCE", "amount": order.advance_amount, "label": "Pay advance"}
    if (order.payment_status == Order.PaymentStatus.ADVANCE_PAID and order.remaining_amount > 0
            and STAGE_ORDER.index(order.status) >= STAGE_ORDER.index(Order.Status.PACKAGING)):
        return {"purpose": "REMAINING", "amount": order.remaining_amount, "label": "Pay remaining amount"}
    return None
