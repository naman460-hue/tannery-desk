"""API tests: auth, roles, and the whole RFQ -> delivery -> review flow.  Run with: python manage.py test"""
from datetime import timedelta
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import User
from common.utils import today
from factories.models import FactoryProfile
from payments import gateway

PASSWORD = "Str0ng!Pass#1"
XHR = {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest"}


def make_user(email, role, **extra):
    return User.objects.create_user(email=email, password=PASSWORD, name=email.split("@")[0], role=role,
                                    phone="+91 98765 43210", city="Kanpur", state="Uttar Pradesh", **extra)


def make_factory(email="f1@test.com", status="VERIFIED", **over):
    user = make_user(email, "FACTORY", company_name="Test Tannery")
    data = dict(user=user, name="Test Tannery", city="Kanpur", state="Uttar Pradesh", leather_types=["Buffalo", "Cow"],
                applications=["Bags"], colors=["Tan"], certifications=["ISO 9001"], min_thickness="1.0",
                max_thickness="2.5", min_order_quantity="500", production_capacity="20000", typical_lead_time_days=20,
                contact_phone="+91 98765 43210", verification_status=status)
    data.update(over)
    return FactoryProfile.objects.create(**data)


def api_for(user):
    c = APIClient()
    res = c.post("/api/auth/login/", {"email": user.email, "password": PASSWORD}, format="json")
    assert res.status_code == 200, res.content
    c.credentials(HTTP_AUTHORIZATION="Bearer " + res.json()["access"])
    return c


def rfq_payload(**over):
    data = dict(leather_type="Buffalo", application="Bags", finish="Aniline", color="Tan", thickness_min="1.8",
                thickness_max="2.0", quantity="4000", unit="SQ_FT", required_date=str(today() + timedelta(days=60)),
                delivery_city="Mumbai", client_token="tok-1")
    data.update(over)
    return data


class AuthTests(TestCase):
    def test_register_client_and_factory(self):
        c = APIClient()
        base = dict(phone="+91 98765 43210", password=PASSWORD, confirm_password=PASSWORD)
        res = c.post("/api/auth/register/", dict(name="Asha", email="asha@test.com", role="CLIENT", **base), format="json")
        self.assertEqual(res.status_code, 201, res.content)
        self.assertIn("access", res.json())
        self.assertTrue(hasattr(User.objects.get(email="asha@test.com"), "client_profile"))
        res = c.post("/api/auth/register/", dict(name="Fac", email="fac@test.com", role="FACTORY",
                                                  company_name="Fac Leathers", **base), format="json")
        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual(User.objects.get(email="fac@test.com").factory_profile.verification_status, "PENDING")

    def test_register_validation(self):
        c = APIClient()
        base = dict(name="A", email="a@test.com", phone="+91 98765 43210", password=PASSWORD,
                    confirm_password=PASSWORD, role="CLIENT")
        post = lambda d: c.post("/api/auth/register/", d, format="json")  # noqa: E731
        self.assertEqual(post({**base, "confirm_password": "x"}).status_code, 400)
        self.assertEqual(post({**base, "password": "12345678", "confirm_password": "12345678"}).status_code, 400)
        self.assertEqual(post({**base, "phone": "abc"}).status_code, 400)
        self.assertEqual(post({**base, "role": "ADMIN"}).status_code, 400)  # cannot self-register as admin
        self.assertEqual(post({**base, "role": "FACTORY"}).status_code, 400)  # factory name required
        self.assertEqual(post(base).status_code, 201)
        res = post(base)
        self.assertEqual(res.status_code, 400)
        self.assertIn("already exists", res.json()["detail"])

    def test_login_refresh_logout(self):
        make_user("c@test.com", "CLIENT")
        c = APIClient()
        self.assertEqual(c.post("/api/auth/login/", {"email": "c@test.com", "password": "wrong"}, format="json").status_code, 401)
        self.assertEqual(c.post("/api/auth/refresh/", **XHR).status_code, 204)
        c.cookies["td_refresh"] = "invalid"
        self.assertEqual(c.post("/api/auth/refresh/", **XHR).status_code, 204)
        res = c.post("/api/auth/login/", {"email": "C@test.com", "password": PASSWORD}, format="json")
        self.assertEqual(res.status_code, 200)
        self.assertIn("td_refresh", res.cookies)
        self.assertEqual(c.post("/api/auth/refresh/").status_code, 403)  # needs the XHR header
        self.assertEqual(c.post("/api/auth/refresh/", **XHR).status_code, 200)
        self.assertEqual(c.post("/api/auth/logout/", **XHR).status_code, 200)

    def test_suspended_and_wrong_portal(self):
        make_user("admin@test.com", "ADMIN")
        user = make_user("s@test.com", "CLIENT")
        c = APIClient()
        login = lambda **d: c.post("/api/auth/login/", {"password": PASSWORD, **d}, format="json").status_code  # noqa: E731
        self.assertEqual(login(email="admin@test.com", portal="CLIENT"), 403)
        self.assertEqual(login(email="admin@test.com", portal="ADMIN"), 200)
        user.is_active = False
        user.save()
        self.assertEqual(login(email="s@test.com"), 403)

    def test_password_reset(self):
        from django.contrib.auth.tokens import default_token_generator
        from django.utils.encoding import force_bytes
        from django.utils.http import urlsafe_base64_encode

        user = make_user("r@test.com", "CLIENT")
        c = APIClient()
        self.assertEqual(c.post("/api/auth/password-reset/", {"email": "nobody@test.com"}, format="json").status_code, 200)
        data = {"uid": urlsafe_base64_encode(force_bytes(user.pk)), "token": default_token_generator.make_token(user),
                "new_password": "An0ther!Pass#9"}
        self.assertEqual(c.post("/api/auth/password-reset/confirm/", {**data, "token": "bad"}, format="json").status_code, 400)
        self.assertEqual(c.post("/api/auth/password-reset/confirm/", data, format="json").status_code, 200)
        user.refresh_from_db()
        self.assertTrue(user.check_password("An0ther!Pass#9"))


class PermissionTests(TestCase):
    def setUp(self):
        self.client_user = make_user("c@test.com", "CLIENT")
        self.factory = make_factory()
        self.admin = make_user("admin@test.com", "ADMIN")

    def test_anonymous_blocked(self):
        c = APIClient()
        for url in ("/api/rfqs/", "/api/orders/", "/api/quotations/", "/api/payments/", "/api/notifications/",
                    "/api/dashboard/", "/api/auth/me/", "/api/factories/admin/", "/api/disputes/"):
            self.assertEqual(c.get(url).status_code, 401, url)

    def test_client_cannot_use_factory_or_admin_apis(self):
        c = api_for(self.client_user)
        for url in ("/api/factories/admin/", "/api/auth/admin/users/", "/api/admin/reports/", "/api/factories/me/",
                    "/api/products/mine/", "/api/products/admin/"):
            self.assertEqual(c.get(url).status_code, 403, url)
        res = c.post(f"/api/factories/admin/{self.factory.pk}/verification/", {"status": "VERIFIED"}, format="json")
        self.assertEqual(res.status_code, 403)

    def test_factory_cannot_use_admin_or_client_apis(self):
        f = api_for(self.factory.user)
        for url in ("/api/factories/admin/", "/api/auth/admin/users/", "/api/admin/reports/"):
            self.assertEqual(f.get(url).status_code, 403, url)
        self.assertEqual(f.post("/api/rfqs/", rfq_payload(), format="json").status_code, 403)
        self.assertEqual(f.post("/api/payments/create/", {"order_id": 1, "purpose": "ADVANCE"}, format="json").status_code, 403)

    def test_admin_verifies_and_suspends(self):
        pending = make_factory("p@test.com", status="PENDING")
        a = api_for(self.admin)
        url = f"/api/factories/admin/{pending.pk}/verification/"
        self.assertEqual(a.post(url, {"status": "REJECTED"}, format="json").status_code, 400)  # reason required
        self.assertEqual(a.post(url, {"status": "VERIFIED"}, format="json").status_code, 200)
        pending.refresh_from_db()
        self.assertEqual(pending.verification_status, "VERIFIED")
        res = a.post(f"/api/auth/admin/users/{self.client_user.pk}/set-active/", {"is_active": False}, format="json")
        self.assertEqual(res.status_code, 200)
        res = APIClient().post("/api/auth/login/", {"email": "c@test.com", "password": PASSWORD}, format="json")
        self.assertEqual(res.status_code, 403)


class WorkflowTests(TestCase):
    """RFQ -> quotation -> accept -> order -> payment -> production -> dispatch -> delivery -> review."""

    def setUp(self):
        self.client_user = make_user("c@test.com", "CLIENT")
        self.fac = make_factory("f1@test.com")
        self.fac2 = make_factory("f2@test.com", name="Second Tannery", certifications=[])
        self.other_client = make_user("c2@test.com", "CLIENT")
        self.c = api_for(self.client_user)
        self.f = api_for(self.fac.user)
        self.f2 = api_for(self.fac2.user)

    def make_rfq(self, **over):
        res = self.c.post("/api/rfqs/", rfq_payload(**over), format="json")
        self.assertIn(res.status_code, (200, 201), res.content)
        return res.json()

    def quote(self, who, rfq_id, price="100", **over):
        data = dict(rfq=rfq_id, price=price, quantity="4000", production_days=20, shipping_days=5,
                    validity_date=str(today() + timedelta(days=10)), notes="ok")
        data.update(over)
        return who.post("/api/quotations/", data, format="json")

    def full_order(self):
        rfq = self.make_rfq()
        q1 = self.quote(self.f, rfq["id"], price="100").json()
        q2 = self.quote(self.f2, rfq["id"], price="90").json()
        res = self.c.post(f"/api/quotations/{q1['id']}/accept/")
        self.assertEqual(res.status_code, 201, res.content)
        return rfq, q1, q2, res.json()["order_id"]

    def pay(self, order_id, purpose):
        res = self.c.post("/api/payments/create/", {"order_id": order_id, "purpose": purpose}, format="json")
        self.assertEqual(res.status_code, 201, res.content)
        return res.json()

    def test_rfq_creation_matching_and_validation(self):
        res = self.c.post("/api/rfqs/", rfq_payload(quantity=""), format="json")
        self.assertEqual(res.status_code, 400)
        self.assertIn("quantity", res.json()["detail"].lower())  # e.g. "Please enter a valid quantity."
        self.assertEqual(self.c.post("/api/rfqs/", rfq_payload(quantity="-5"), format="json").status_code, 400)
        self.assertEqual(self.c.post("/api/rfqs/", rfq_payload(required_date=str(today())), format="json").status_code, 400)
        self.assertEqual(self.c.post("/api/rfqs/", rfq_payload(leather_type="Dragon"), format="json").status_code, 400)
        rfq = self.make_rfq()
        self.assertTrue(rfq["number"].startswith("RFQ-"))
        self.assertEqual(rfq["status"], "MATCHING")
        self.assertEqual(self.make_rfq()["id"], rfq["id"])  # same wizard submitted twice -> same RFQ
        self.assertTrue(self.fac.user.notifications.filter(title="New RFQ available").exists())
        res = self.c.post("/api/rfqs/", rfq_payload(leather_type="Sheep", client_token="tok-2"), format="json")
        self.assertEqual(res.json()["status"], "SUBMITTED")  # nobody makes sheep leather

    def test_clients_only_see_their_own_rfqs(self):
        rfq = self.make_rfq()
        other = api_for(self.other_client)
        self.assertEqual(other.get(f"/api/rfqs/{rfq['id']}/").status_code, 404)
        self.assertEqual(other.get("/api/rfqs/").json()["count"], 0)

    def test_factory_quotation_rules(self):
        rfq = self.make_rfq(required_certifications=["ISO 9001"])
        unmatched = make_factory("f3@test.com", name="Sheep only", leather_types=["Sheep"])
        self.assertEqual(self.quote(api_for(unmatched.user), rfq["id"]).status_code, 400)
        pending = make_factory("f4@test.com", status="PENDING")
        self.assertEqual(self.quote(api_for(pending.user), rfq["id"]).status_code, 403)
        self.assertEqual(self.quote(self.f, rfq["id"], price="0").status_code, 400)
        res = self.quote(self.f, rfq["id"])
        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual(self.quote(self.f, rfq["id"]).status_code, 400)  # duplicate
        qid = res.json()["id"]
        self.assertEqual(self.f.patch(f"/api/quotations/{qid}/", {"price": "95"}, format="json").status_code, 200)
        self.assertEqual(self.c.get(f"/api/rfqs/{rfq['id']}/").json()["status"], "QUOTATION_RECEIVED")
        listing = self.c.get(f"/api/quotations/?rfq={rfq['id']}").json()["results"]
        self.assertEqual(len(listing), 1)
        self.assertTrue(listing[0]["recommended"])
        self.assertNotIn("contact_phone", listing[0]["factory"])
        self.assertEqual(self.c.patch(f"/api/quotations/{qid}/", {"price": "1"}, format="json").status_code, 403)
        self.assertEqual(api_for(self.other_client).post(f"/api/quotations/{qid}/accept/").status_code, 404)

    def test_accept_quotation_creates_order(self):
        rfq, q1, q2, order_id = self.full_order()
        order = self.c.get(f"/api/orders/{order_id}/").json()
        self.assertEqual(order["status"], "ORDER_CREATED")
        self.assertEqual(Decimal(order["total_amount"]), Decimal("400000.00"))
        self.assertEqual(Decimal(order["advance_amount"]) + Decimal(order["remaining_amount"]), Decimal("400000.00"))
        self.assertEqual(order["next_payment"]["purpose"], "ADVANCE")
        statuses = {q["id"]: q["status"] for q in self.f.get("/api/quotations/").json()["results"]}
        self.assertEqual(statuses[q1["id"]], "ACCEPTED")
        self.assertEqual(self.f2.get("/api/quotations/").json()["results"][0]["status"], "CLOSED")
        self.assertEqual(self.c.get(f"/api/rfqs/{rfq['id']}/").json()["status"], "ORDER_CREATED")
        self.assertTrue(self.client_user.notifications.filter(title="Quotation accepted").exists())
        self.assertTrue(self.fac.user.notifications.filter(title="Your quotation was accepted").exists())
        self.assertEqual(self.c.post(f"/api/quotations/{q1['id']}/accept/").status_code, 400)
        self.assertEqual(self.c.post(f"/api/quotations/{q2['id']}/accept/").status_code, 400)
        self.assertIn("client", self.f.get(f"/api/orders/{order_id}/").json()["parties"])
        self.assertEqual(self.f2.get(f"/api/orders/{order_id}/").status_code, 404)

    def test_payment_verification(self):
        _, _, _, order_id = self.full_order()
        res = self.c.post("/api/payments/create/", {"order_id": order_id, "purpose": "REMAINING"}, format="json")
        self.assertEqual(res.status_code, 400)
        p = self.pay(order_id, "ADVANCE")
        self.assertTrue(p["sandbox"])
        self.assertEqual(self.pay(order_id, "ADVANCE")["payment_id"], p["payment_id"])  # no duplicate attempts
        with override_settings(PAYMENTS_SANDBOX=False):
            res = self.c.post(f"/api/payments/{p['payment_id']}/sandbox/", {"outcome": "success"}, format="json")
            self.assertEqual(res.status_code, 404)
        bad = self.c.post("/api/payments/verify/", {"razorpay_order_id": p["razorpay_order_id"],
                                                    "razorpay_payment_id": "pay_x", "razorpay_signature": "nope"},
                          format="json")
        self.assertEqual(bad.status_code, 400)  # a made-up signature must not mark anything as paid
        self.assertEqual(self.c.get(f"/api/orders/{order_id}/").json()["payment_status"], "PENDING")
        p = self.pay(order_id, "ADVANCE")  # fresh attempt after the failed one
        sig = gateway.sign(p["razorpay_order_id"], "pay_ok")
        body = {"razorpay_order_id": p["razorpay_order_id"], "razorpay_payment_id": "pay_ok", "razorpay_signature": sig}
        self.assertEqual(self.c.post("/api/payments/verify/", body, format="json").status_code, 200)
        order = self.c.get(f"/api/orders/{order_id}/").json()
        self.assertEqual(order["payment_status"], "ADVANCE_PAID")
        self.assertEqual(order["status"], "PAYMENT_RECEIVED")
        self.assertEqual(self.c.post("/api/payments/verify/", body, format="json").status_code, 200)  # idempotent
        self.assertEqual(len(self.c.get("/api/payments/?status=PAID").json()["results"]), 1)

    def test_production_dispatch_delivery_review(self):
        _, _, _, order_id = self.full_order()
        url = f"/api/orders/{order_id}/"
        prod = {"stage": "PRODUCTION_STARTED", "percentage": 10, "message": "Started"}
        self.assertEqual(self.f.post(url + "production/", prod, format="json").status_code, 400)  # advance unpaid
        self.assertEqual(self.c.post(url + "production/", prod, format="json").status_code, 403)  # client cannot
        p = self.pay(order_id, "ADVANCE")
        sandbox = lambda pid: self.c.post(f"/api/payments/{pid}/sandbox/", {"outcome": "success"}, format="json")  # noqa: E731
        self.assertEqual(sandbox(p["payment_id"]).status_code, 200)
        res = self.f.post(url + "production/", prod, format="json")
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.json()["status"], "PRODUCTION_STARTED")
        self.assertEqual(self.f.post(url + "production/", {**prod, "percentage": 5}, format="json").status_code, 400)
        self.assertEqual(self.f.post(url + "production/", {"stage": "IN_TRANSIT", "percentage": 100}, format="json").status_code, 400)
        self.assertEqual(self.f.post(url + "production/", {"stage": "QUALITY_CHECK", "percentage": 60}, format="json").status_code, 200)
        self.assertEqual(self.f.post(url + "production/", {"stage": "PACKAGING", "percentage": 95}, format="json").status_code, 200)
        dispatch = {"courier_name": "BlueDart", "tracking_number": "BD1"}
        self.assertEqual(self.f.post(url + "dispatch/", dispatch, format="json").status_code, 400)  # not ready yet
        self.assertEqual(self.f.post(url + "ready-for-dispatch/").status_code, 200)
        self.assertEqual(self.f.post(url + "dispatch/", dispatch, format="json").status_code, 200)
        self.assertEqual(self.f.post(url + "production/", {"stage": "IN_TRANSIT", "percentage": 100}, format="json").status_code, 200)
        self.assertEqual(self.f.post(url + "production/", {"stage": "DELIVERED", "percentage": 100}, format="json").status_code, 200)
        self.assertEqual(self.c.post(url + "confirm-delivery/").status_code, 400)  # remaining payment due first
        p2 = self.pay(order_id, "REMAINING")
        self.assertEqual(sandbox(p2["payment_id"]).status_code, 200)
        self.assertEqual(self.c.get(url).json()["payment_status"], "PAID")
        self.assertEqual(self.c.post(url + "confirm-delivery/").status_code, 200)
        self.assertEqual(self.c.get(url).json()["status"], "COMPLETED")
        self.assertEqual(self.c.post("/api/reviews/create/", {"order": order_id, "rating": 9}, format="json").status_code, 400)
        res = self.c.post("/api/reviews/create/", {"order": order_id, "rating": 4, "review": "Good"}, format="json")
        self.assertEqual(res.status_code, 201, res.content)
        self.fac.refresh_from_db()
        self.assertEqual(self.fac.review_count, 1)
        self.assertEqual(self.c.post("/api/reviews/create/", {"order": order_id, "rating": 5}, format="json").status_code, 400)

    def test_failed_payment_and_messages(self):
        _, _, _, order_id = self.full_order()
        p = self.pay(order_id, "ADVANCE")
        res = self.c.post(f"/api/payments/{p['payment_id']}/sandbox/", {"outcome": "fail"}, format="json")
        self.assertEqual(res.json()["status"], "FAILED")
        self.assertEqual(self.c.get(f"/api/orders/{order_id}/").json()["payment_status"], "PENDING")
        self.assertEqual(self.c.post("/api/messages/", {"order": order_id, "body": "Hello"}, format="json").status_code, 201)
        self.assertEqual(self.c.post("/api/messages/", {"order": order_id, "body": ""}, format="json").status_code, 400)
        self.assertEqual(len(self.f.get(f"/api/messages/?order={order_id}").json()), 1)
        self.assertEqual(self.f2.get(f"/api/messages/?order={order_id}").status_code, 404)

    def test_file_upload_validation(self):
        rfq = self.make_rfq()
        url = f"/api/rfqs/{rfq['id']}/attachments/"
        bad = SimpleUploadedFile("evil.exe", b"MZ\x90\x00", content_type="application/octet-stream")
        self.assertEqual(self.c.post(url, {"file": bad}, format="multipart").status_code, 400)
        fake = SimpleUploadedFile("spec.pdf", b"not really a pdf", content_type="application/pdf")
        self.assertEqual(self.c.post(url, {"file": fake}, format="multipart").status_code, 400)
        good = SimpleUploadedFile("spec.pdf", b"%PDF-1.4 test", content_type="application/pdf")
        res = self.c.post(url, {"file": good}, format="multipart")
        self.assertEqual(res.status_code, 201, res.content)
        att = res.json()["attachments"][0]
        self.assertEqual(self.c.get(att["download_url"]).status_code, 200)
        self.assertEqual(api_for(self.other_client).get(att["download_url"]).status_code, 404)

    def test_catalog_filters_and_search(self):
        from products.models import LeatherProduct

        LeatherProduct.objects.create(factory=self.fac, name="Buffalo Tan", leather_type="Buffalo", finish="Aniline",
                                      application="Bags", color="Tan", thickness_min="1.8", thickness_max="2.0",
                                      moq="800", lead_time_days=28, certifications="ISO 9001, REACH")
        pend = make_factory("p@test.com", status="PENDING")
        LeatherProduct.objects.create(factory=pend, name="Hidden", leather_type="Cow", finish="Suede",
                                      application="Bags", color="Tan", thickness_min="1", thickness_max="1.2",
                                      moq="100", lead_time_days=10)
        anon = APIClient()
        self.assertEqual(anon.get("/api/products/").json()["count"], 1)  # unverified factory's product is hidden
        self.assertEqual(anon.get("/api/products/?leather_type=Buffalo&certification=REACH").json()["count"], 1)
        self.assertEqual(anon.get("/api/products/?leather_type=Cow").json()["count"], 0)
        self.assertEqual(anon.get("/api/products/?moq=500").json()["count"], 0)
        self.assertEqual(anon.get("/api/products/?thickness_min=1.9&thickness_max=2.5").json()["count"], 1)
        self.assertEqual(anon.get("/api/products/?thickness_min=abc").status_code, 400)
        res = anon.get("/api/search/?q=buffalo").json()
        self.assertEqual(len(res["products"]), 1)
        self.assertEqual(res["rfqs"], [])
        self.assertIn("Buffalo", anon.get("/api/meta/options/").json()["leather_types"])
