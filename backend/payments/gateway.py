"""Razorpay wrapper.

* With RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET set, real Razorpay orders are created and signatures are checked with the secret.
* Without keys the app runs in SANDBOX mode: nothing is sent to Razorpay, and the server itself plays the part of the
  gateway. The same signature check is used in both modes, so the verification code path is identical.
The secret never leaves the server; the browser only ever receives the public key id.
"""
import hashlib
import hmac
import secrets
from decimal import Decimal

from django.conf import settings


class GatewayError(Exception):
    pass


def is_sandbox():
    return settings.PAYMENTS_SANDBOX


def _secret():
    return settings.SANDBOX_SIGNING_SECRET if is_sandbox() else settings.RAZORPAY_KEY_SECRET


def to_paise(amount):
    return int((Decimal(amount) * 100).quantize(Decimal("1")))


def create_gateway_order(amount, receipt, notes=None):
    """Returns the gateway order id."""
    if is_sandbox():
        return "order_sandbox_" + secrets.token_hex(8)
    try:
        import razorpay

        client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
        data = client.order.create({"amount": to_paise(amount), "currency": "INR", "receipt": receipt[:40],
                                    "notes": notes or {}})
        return data["id"]
    except Exception as exc:  # network problems, bad keys...
        raise GatewayError("We could not reach the payment provider. Please try again.") from exc


def sign(order_id, payment_id):
    return hmac.new(_secret().encode(), f"{order_id}|{payment_id}".encode(), hashlib.sha256).hexdigest()


def signature_is_valid(order_id, payment_id, signature):
    if not (order_id and payment_id and signature):
        return False
    return hmac.compare_digest(sign(order_id, payment_id), str(signature))


def webhook_signature_is_valid(raw_body, signature):
    secret = settings.RAZORPAY_WEBHOOK_SECRET
    if not secret or not signature:
        return False
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
