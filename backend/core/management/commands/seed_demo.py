"""Creates clearly-marked DEMO data: one client, one admin, four factories, products, RFQs, quotations and an order.

    python manage.py seed_demo            # create (skips if demo data exists)
    python manage.py seed_demo --reset    # delete demo data first, then create it again
"""
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import ClientProfile, User
from common.utils import today
from factories.models import FactoryProfile, Verification
from orders.models import Dispute, Order, ProductionUpdate
from orders.services import accept_quotation
from payments.models import Payment
from payments.services import mark_paid
from products.models import LeatherProduct
from rfqs.models import FactoryQuotation, RFQ, RFQMatch
from rfqs.services import submit_rfq

DEMO_PASSWORD = "DemoPass#2026"
DOMAIN = "demo.tannerydesk.test"

FACTORIES = [
    dict(email=f"ganga@{DOMAIN}", name="Rakesh Verma", company="Ganga Tanning Works [DEMO]", city="Kanpur",
         state="Uttar Pradesh", types=["Cow", "Buffalo"], apps=["Footwear", "Bags", "Furniture"],
         colors=["Black", "Brown", "Tan"], certs=["LWG Gold", "ISO 9001"], thick=("0.8", "2.2"), moq="500",
         cap="20000", lead=21, status=Verification.VERIFIED),
    dict(email=f"coromandel@{DOMAIN}", name="S. Narayanan", company="Coromandel Hides [DEMO]", city="Chennai",
         state="Tamil Nadu", types=["Buffalo", "Cow"], apps=["Bags", "Accessories", "Footwear"],
         colors=["Brown", "Tan", "Black", "Red"], certs=["ISO 9001", "REACH"], thick=("1.0", "2.4"), moq="800",
         cap="15000", lead=28, status=Verification.VERIFIED),
    dict(email=f"pinnacle@{DOMAIN}", name="A. Rahman", company="Pinnacle Leathers [DEMO]", city="Ambur",
         state="Tamil Nadu", types=["Cow", "Goat", "Sheep"], apps=["Automotive", "Furniture", "Garments", "Accessories"],
         colors=["Black", "Blue", "Red", "Green"], certs=["IATF 16949", "LWG Silver", "REACH"], thick=("0.7", "1.6"),
         moq="300", cap="30000", lead=18, status=Verification.VERIFIED),
    dict(email=f"deccan@{DOMAIN}", name="Ravi Kumar", company="Deccan Hide Co. [DEMO]", city="Ambur",
         state="Tamil Nadu", types=[], apps=[], colors=[], certs=[], thick=(None, None), moq=None, cap=None,
         lead=None, status=Verification.PENDING),
]

PRODUCTS = [
    ("Full Grain Cow Nappa", 0, "Cow", "Full Grain", "Footwear", "Brown", "1.4", "1.6", "500", 21, "LWG Gold", True),
    ("Buffalo Distressed Tan", 1, "Buffalo", "Aniline", "Bags", "Tan", "1.8", "2.0", "800", 28, "ISO 9001", True),
    ("Goat Suede Velvet", 2, "Goat", "Suede", "Garments", "Blue", "0.8", "1.0", "300", 18, "REACH", False),
    ("Corrected Grain Automotive Hide", 2, "Cow", "Corrected Grain", "Automotive", "Black", "1.2", "1.4", "2000", 35,
     "IATF 16949", True),
    ("Semi-Aniline Furniture Hide", 0, "Cow", "Semi-Aniline", "Furniture", "Red", "1.1", "1.3", "1500", 30,
     "LWG Silver", False),
    ("Sheep Nubuck Soft", 2, "Sheep", "Nubuck", "Accessories", "Green", "0.7", "0.9", "250", 16, "REACH", True),
]


class Command(BaseCommand):
    help = "Create demo accounts and data (all marked as demo)."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Delete existing demo data first")

    @transaction.atomic
    def handle(self, *args, **opts):
        if opts["reset"]:
            self._reset()
        if User.objects.filter(is_demo=True).exists():
            self.stdout.write(self.style.WARNING("Demo data already exists. Use --reset to rebuild it."))
            return

        admin = User.objects.create_user(email=f"admin@{DOMAIN}", password=DEMO_PASSWORD, name="Demo Admin [DEMO]",
                                         role="ADMIN", is_staff=True, is_demo=True, city="Kanpur", state="Uttar Pradesh")
        client = User.objects.create_user(
            email=f"client@{DOMAIN}", password=DEMO_PASSWORD, name="Priya Nair", role="CLIENT", is_demo=True,
            company_name="Urban Carry Bags [DEMO]", phone="+91 98765 43210", city="Mumbai", state="Maharashtra",
            address="12 Linking Road, Bandra")
        ClientProfile.objects.create(user=client, industry="Bags and accessories")

        factories = []
        for f in FACTORIES:
            phone = "+91 90000 1%04d" % (len(factories) + 1)
            user = User.objects.create_user(email=f["email"], password=DEMO_PASSWORD, name=f["name"], role="FACTORY",
                                            is_demo=True, company_name=f["company"], city=f["city"], state=f["state"],
                                            phone=phone)
            lo, hi = f["thick"]
            factories.append(FactoryProfile.objects.create(
                user=user, name=f["company"], city=f["city"], state=f["state"], description="Demo factory profile.",
                contact_name=f["name"], contact_phone=phone, contact_email=user.email, leather_types=f["types"],
                applications=f["apps"], colors=f["colors"], certifications=f["certs"], min_thickness=lo,
                max_thickness=hi, min_order_quantity=f["moq"], production_capacity=f["cap"],
                typical_lead_time_days=f["lead"], verification_status=f["status"]))

        for name, fi, ltype, finish, app, color, tmin, tmax, moq, lead, cert, sample in PRODUCTS:
            LeatherProduct.objects.create(
                factory=factories[fi], name=name, leather_type=ltype, finish=finish, application=app, color=color,
                thickness_min=tmin, thickness_max=tmax, moq=moq, lead_time_days=lead, certifications=cert,
                sample_available=sample, description="Demo product.")

        def make_rfq(**kw):
            base = dict(client=client, unit="SQ_FT", delivery_city="Mumbai", delivery_state="Maharashtra",
                        required_date=today() + timedelta(days=75), need="Finished Leather")
            base.update(kw)
            rfq = RFQ.objects.create(**base)
            rfq.refresh_from_db()
            submit_rfq(rfq)
            return rfq

        def quote(rfq, factory, price, prod_days, ship_days, notes):
            q = FactoryQuotation.objects.create(
                rfq=rfq, factory=factory, price=price, price_unit=rfq.unit, quantity=rfq.quantity,
                moq=factory.min_order_quantity, production_days=prod_days, shipping_days=ship_days, notes=notes,
                validity_date=today() + timedelta(days=14))
            RFQMatch.objects.filter(rfq=rfq, factory=factory).update(response=RFQMatch.Response.QUOTED)
            if rfq.status in (RFQ.Status.SUBMITTED, RFQ.Status.MATCHING):
                rfq.status = RFQ.Status.QUOTATION_RECEIVED
                rfq.save(update_fields=["status"])
            return q

        # 1. Two quotations waiting for the client to compare
        rfq1 = make_rfq(leather_type="Buffalo", application="Bags", finish="Aniline", color="Tan", thickness_min="1.8",
                        thickness_max="2.0", quantity=Decimal("4000"), requirements="Distressed look, even dye.",
                        target_price=Decimal("120"))
        quote(rfq1, factories[0], Decimal("118.50"), 21, 6, "Includes 2 free swatches.")
        quote(rfq1, factories[1], Decimal("112.00"), 28, 5, "Price valid for the full lot only.")

        # 2. A brand-new RFQ with no quotations yet
        make_rfq(leather_type="Goat", application="Garments", finish="Suede", color="Blue", thickness_min="0.8",
                 thickness_max="1.0", quantity=Decimal("1200"), required_certifications=["REACH"])

        # 3. An order already in production (advance paid, at Quality Check)
        rfq3 = make_rfq(leather_type="Cow", application="Footwear", finish="Full Grain", color="Brown",
                        thickness_min="1.4", thickness_max="1.6", quantity=Decimal("6000"))
        q3 = quote(rfq3, factories[0], Decimal("95.00"), 21, 7, "Standard nappa lot.")
        order = accept_quotation(q3.pk, client)
        payment = Payment.objects.create(order=order, payer=client, purpose="ADVANCE", amount=order.advance_amount,
                                         mode="SANDBOX", razorpay_order_id="order_sandbox_demo0001")
        mark_paid(payment.pk, "pay_sandbox_demo0001", "demo")
        order.refresh_from_db()
        for stage, pct, msg in (("PRODUCTION_STARTED", 20, "Hides selected and in the drum."),
                                ("PRODUCTION_STARTED", 70, "Finishing line running."),
                                ("QUALITY_CHECK", 85, "Inspection in progress.")):
            ProductionUpdate.objects.create(order=order, stage=stage, percentage=pct, message=msg,
                                            updated_by=factories[0].user)
            order.status, order.progress_percent = stage, pct
        order.save()

        self.stdout.write(self.style.SUCCESS("Demo data created. All demo accounts use the password: " + DEMO_PASSWORD))
        for email, role in [(admin.email, "ADMIN"), (client.email, "CLIENT")] + [(f["email"], "FACTORY") for f in FACTORIES]:
            self.stdout.write(f"  {role:8} {email}")

    def _reset(self):
        Dispute.objects.filter(raised_by__is_demo=True).delete()
        Payment.objects.filter(payer__is_demo=True).delete()
        Order.objects.filter(client__is_demo=True).delete()
        RFQ.objects.filter(client__is_demo=True).delete()
        LeatherProduct.objects.filter(factory__user__is_demo=True).delete()
        User.objects.filter(is_demo=True).delete()
