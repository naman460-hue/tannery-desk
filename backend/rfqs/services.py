from django.db import transaction

from core.activity import log_activity
from notifications.services import notify, notify_admins

from .matching import find_matches
from .models import RFQ, RFQMatch


@transaction.atomic
def submit_rfq(rfq, first_time=True):
    """Match the RFQ with suitable factories, tell everyone concerned, and move it to 'Factory Matching'."""
    existing = set(rfq.matches.values_list("factory_id", flat=True))
    new_factories = []
    for factory, score, reasons in find_matches(rfq):
        if factory.id in existing:
            continue
        RFQMatch.objects.create(rfq=rfq, factory=factory, score=score, reasons=reasons)
        new_factories.append(factory)
    if rfq.status == RFQ.Status.SUBMITTED and rfq.matches.exists():
        rfq.status = RFQ.Status.MATCHING
        rfq.save(update_fields=["status", "updated_at"])
    for factory in new_factories:
        notify(factory.user, "New RFQ available",
               f"{rfq.number}: {rfq.title}, {rfq.quantity:g} {rfq.get_unit_display_label()}.", "RFQ", f"#/rfqs/{rfq.pk}")
    if first_time:
        if new_factories:
            plural = "y" if len(new_factories) == 1 else "ies"
            text = f"{rfq.number} was sent to {len(new_factories)} matching factor{plural}."
        else:
            text = f"{rfq.number} was submitted. We are looking for suitable factories."
        notify(rfq.client, "Your RFQ has been submitted", text, "RFQ", f"#/rfqs/{rfq.pk}")
        notify_admins("New RFQ", f"{rfq.number} from {rfq.client.company_name or rfq.client.name}"
                      + ("" if new_factories else " has no matching factory yet. Please assign one."),
                      "RFQ", f"#/rfqs/{rfq.pk}")
        log_activity(rfq.client, f"Submitted {rfq.number} ({rfq.title})")
    return new_factories
