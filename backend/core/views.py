from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db.models import Count, Q, Sum
from django.utils import timezone
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from common import choices
from common.permissions import IsAdminRole
from factories.models import FactoryProfile
from orders.models import STAGE_ORDER, Dispute, Order
from orders.services import next_payment
from orders.views import orders_for
from payments.models import Payment
from products.views import filter_products, marketplace_products
from rfqs.models import FactoryQuotation, RFQ, RFQMatch
from rfqs.views import rfq_queryset_for

from .models import ActivityLog

OPEN_RFQ = [RFQ.Status.SUBMITTED, RFQ.Status.MATCHING, RFQ.Status.QUOTATION_RECEIVED]
CLOSED_ORDER = [Order.Status.COMPLETED, Order.Status.CANCELLED]
IN_PRODUCTION = [Order.Status.PRODUCTION_STARTED, Order.Status.QUALITY_CHECK, Order.Status.PACKAGING]


class OptionsView(APIView):
    """Lookup lists for forms and filters, so the frontend has no hard-coded business data."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        locations = FactoryProfile.objects.marketplace().exclude(city="").values_list("city", flat=True).distinct()
        labels = dict(Order.Status.choices)
        return Response({
            "needs": choices.NEEDS,
            "leather_types": choices.LEATHER_TYPES,
            "applications": choices.APPLICATIONS,
            "finishes": choices.FINISHES,
            "colors": [{"name": n, "hex": h} for n, h in choices.COLORS.items()],
            "units": [{"value": v, "label": l} for v, l in choices.UNITS],
            "thickness_bands": choices.THICKNESS_BANDS,
            "certifications": choices.CERTIFICATIONS,
            "document_kinds": choices.DOCUMENT_KINDS,
            "order_document_kinds": choices.ORDER_DOCUMENT_KINDS,
            "locations": sorted(set(locations)),
            "rfq_stages": [{"value": v, "label": l} for v, l in RFQ.Status.choices if v != "CANCELLED"],
            "order_stages": [{"value": s, "label": labels[s]} for s in STAGE_ORDER],
            "advance_percent": settings.ADVANCE_PERCENT,
            "payments_sandbox": settings.PAYMENTS_SANDBOX,
            "max_upload_mb": settings.MAX_UPLOAD_MB,
        })


class DashboardView(APIView):
    def get(self, request):
        user = request.user
        if user.role == "CLIENT":
            orders = orders_for(user)
            live = orders.exclude(status__in=CLOSED_ORDER)
            return Response({
                "active_rfqs": rfq_queryset_for(user).filter(status__in=OPEN_RFQ).count(),
                "quotes_to_review": rfq_queryset_for(user).filter(status=RFQ.Status.QUOTATION_RECEIVED).count(),
                "active_orders": live.count(),
                "payments_due": sum(1 for o in live if next_payment(o)),
                "completed_orders": orders.filter(status=Order.Status.COMPLETED).count(),
            })
        if user.role == "FACTORY":
            fp = user.factory_profile
            orders = orders_for(user)
            matches = RFQMatch.objects.filter(factory=fp, rfq__status__in=OPEN_RFQ)
            quotes = FactoryQuotation.objects.filter(factory=fp)
            return Response({
                "verification_status": fp.verification_status,
                "verification_note": fp.verification_note,
                "profile_complete": fp.is_profile_complete,
                "new_rfqs": matches.filter(response=RFQMatch.Response.NEW).count(),
                "relevant_rfqs": matches.exclude(response=RFQMatch.Response.DECLINED).count(),
                "submitted_quotations": quotes.filter(status=FactoryQuotation.Status.SUBMITTED).count(),
                "accepted_quotations": quotes.filter(status=FactoryQuotation.Status.ACCEPTED).count(),
                "active_orders": orders.exclude(status__in=CLOSED_ORDER).count(),
                "production_orders": orders.filter(status__in=IN_PRODUCTION).count(),
                "completed_orders": orders.filter(status=Order.Status.COMPLETED).count(),
                "orders_needing_update": orders.filter(status=Order.Status.PAYMENT_RECEIVED).count(),
            })
        paid = Payment.objects.filter(status=Payment.Status.PAID).aggregate(total=Sum("amount"), n=Count("id"))
        return Response({
            "total_clients": User.objects.filter(role="CLIENT").count(),
            "total_factories": FactoryProfile.objects.count(),
            "active_rfqs": RFQ.objects.filter(status__in=OPEN_RFQ).count(),
            "rfqs_without_factory": RFQ.objects.filter(status__in=OPEN_RFQ, matches__isnull=True).count(),
            "active_orders": Order.objects.exclude(status__in=CLOSED_ORDER).count(),
            "completed_orders": Order.objects.filter(status=Order.Status.COMPLETED).count(),
            "pending_factories": FactoryProfile.objects.filter(verification_status="PENDING").count(),
            "payments_total": str(paid["total"] or Decimal("0")),
            "payments_count": paid["n"],
            "open_disputes": Dispute.objects.exclude(status__in=["RESOLVED", "CLOSED"]).count(),
            "recent_activities": [
                {"id": a.id, "action": a.action, "actor": a.actor.name if a.actor else "System",
                 "created_at": a.created_at}
                for a in ActivityLog.objects.select_related("actor")[:10]
            ],
        })


class SearchView(APIView):
    """One search box for products, factories, RFQs and orders (RFQs and orders only when signed in)."""

    permission_classes = [AllowAny]

    def get(self, request):
        q = (request.query_params.get("q") or "").strip()
        result = {"q": q, "products": [], "factories": [], "rfqs": [], "orders": []}
        if len(q) < 2:
            return Response(result)
        user = request.user
        products = filter_products(marketplace_products(), {"q": q})[:5]
        factories = FactoryProfile.objects.marketplace().filter(
            Q(name__icontains=q) | Q(city__icontains=q) | Q(state__icontains=q))[:5]
        result["products"] = [{"id": p.id, "name": p.name, "sub": f"{p.leather_type} · {p.application} · {p.factory.city}"}
                              for p in products]
        result["factories"] = [{"id": f.id, "name": f.name, "sub": f"{f.city}, {f.state}"} for f in factories]
        if user and user.is_authenticated:
            rfqs = rfq_queryset_for(user).filter(
                Q(number__icontains=q) | Q(leather_type__icontains=q) | Q(application__icontains=q)
                | Q(color__icontains=q)).distinct()[:5]
            orders = orders_for(user).filter(
                Q(number__icontains=q) | Q(rfq__number__icontains=q) | Q(factory__name__icontains=q))[:5]
            result["rfqs"] = [{"id": r.id, "name": r.number, "sub": f"{r.title} · {r.get_status_display()}"} for r in rfqs]
            result["orders"] = [{"id": o.id, "name": o.number, "sub": f"{o.rfq.title} · {o.get_status_display()}"}
                                for o in orders]
        return Response(result)


class AdminReportsView(APIView):
    permission_classes = [IsAdminRole]

    def get(self, request):
        since = timezone.now() - timedelta(days=30)
        pay = Payment.objects.values("status").annotate(n=Count("id"), total=Sum("amount"))
        top = (Order.objects.filter(status=Order.Status.COMPLETED).values("factory__name")
               .annotate(n=Count("id"), value=Sum("total_amount")).order_by("-value")[:5])
        return Response({
            "rfq_by_status": {r["status"]: r["n"] for r in RFQ.objects.values("status").annotate(n=Count("id"))},
            "order_by_status": {r["status"]: r["n"] for r in Order.objects.values("status").annotate(n=Count("id"))},
            "payments_by_status": {p["status"]: {"count": p["n"], "total": str(p["total"] or 0)} for p in pay},
            "top_factories": [{"name": t["factory__name"], "orders": t["n"], "value": str(t["value"])} for t in top],
            "last_30_days": {
                "new_clients": User.objects.filter(role="CLIENT", created_at__gte=since).count(),
                "new_factories": User.objects.filter(role="FACTORY", created_at__gte=since).count(),
                "new_rfqs": RFQ.objects.filter(created_at__gte=since).count(),
                "new_orders": Order.objects.filter(created_at__gte=since).count(),
            },
        })
