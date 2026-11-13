from django.contrib.auth import get_user_model

from .models import Notification


def notify(user, title, message, type="SYSTEM", link=""):
    if user is None:
        return None
    return Notification.objects.create(user=user, title=title[:160], message=message[:400], type=type, link=link)


def notify_many(users, title, message, type="SYSTEM", link=""):
    Notification.objects.bulk_create(
        [Notification(user=u, title=title[:160], message=message[:400], type=type, link=link) for u in users])


def notify_admins(title, message, type="SYSTEM", link=""):
    notify_many(get_user_model().objects.filter(role="ADMIN", is_active=True), title, message, type, link)
