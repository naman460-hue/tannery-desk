"""Simple factory matching: a weighted score out of 100. No AI, just clear rules.

  Leather type  25   (must match, otherwise the factory is not considered)
  Application   20
  MOQ           15   (factory minimum is not above the quantity requested)
  Certification 10   (all required certifications held; full marks if none required)
  Lead time     10   (typical lead time fits before the required date)
  Thickness      5
  Color          5
  Location       5   (same city 5, same state 3)
  Capacity       5   (monthly capacity covers the quantity)
Factories scoring below MIN_SCORE are not sent the RFQ. The best MAX_MATCHES are kept.
"""
from decimal import Decimal

from common.utils import today
from factories.models import FactoryProfile

MIN_SCORE = 40
MAX_MATCHES = 10


def score_factory(rfq, factory):
    score, reasons = 0, []
    if rfq.leather_type not in (factory.leather_types or []):
        return 0, []
    score += 25
    reasons.append(f"Makes {rfq.leather_type} leather")
    if rfq.application in (factory.applications or []):
        score += 20
        reasons.append(f"Experience in {rfq.application.lower()}")
    if factory.min_order_quantity is not None and factory.min_order_quantity <= rfq.quantity:
        score += 15
        reasons.append("Your quantity meets their minimum order")
    required = set(rfq.required_certifications or [])
    if not required or required.issubset(set(factory.certifications or [])):
        score += 10
        if required:
            reasons.append("Holds the certifications you asked for")
    if factory.typical_lead_time_days is not None:
        if factory.typical_lead_time_days <= (rfq.required_date - today()).days:
            score += 10
            reasons.append(f"Typical lead time {factory.typical_lead_time_days} days fits your date")
    if factory.min_thickness is not None and factory.max_thickness is not None:
        if factory.min_thickness <= rfq.thickness_max and factory.max_thickness >= rfq.thickness_min:
            score += 5
            reasons.append("Can make your thickness")
    if rfq.color in (factory.colors or []):
        score += 5
        reasons.append(f"Offers {rfq.color.lower()}")
    if rfq.delivery_city and factory.city and rfq.delivery_city.strip().lower() == factory.city.strip().lower():
        score += 5
        reasons.append("Same city as your delivery location")
    elif rfq.delivery_state and factory.state and rfq.delivery_state.strip().lower() == factory.state.strip().lower():
        score += 3
        reasons.append("Same state as your delivery location")
    if factory.production_capacity is not None and factory.production_capacity >= rfq.quantity:
        score += 5
        reasons.append("Capacity covers your quantity")
    return score, reasons


def find_matches(rfq):
    results = []
    for factory in FactoryProfile.objects.marketplace():
        score, reasons = score_factory(rfq, factory)
        if score >= MIN_SCORE:
            results.append((factory, score, reasons))
    results.sort(key=lambda item: (-item[1], item[0].name))
    return results[:MAX_MATCHES]


def recommendation_score(match_score, price, cheapest_price, rating):
    """Used on the comparison table: 60% fit, 30% price, 10% rating."""
    price_part = Decimal(100) * (cheapest_price / price) if price else Decimal(0)
    rating_part = Decimal(rating or 0) / Decimal(5) * Decimal(100)
    return float(Decimal("0.6") * Decimal(match_score) + Decimal("0.3") * price_part + Decimal("0.1") * rating_part)
