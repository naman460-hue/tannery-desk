from decimal import Decimal, InvalidOperation

from rest_framework.exceptions import ValidationError


def parse_decimal(value, field):
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValidationError({field: ["Please enter a valid number."]})


def today():
    from django.utils import timezone

    return timezone.localdate()


def money(value):
    return Decimal(value).quantize(Decimal("0.01"))
