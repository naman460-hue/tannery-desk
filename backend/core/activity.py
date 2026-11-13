from .models import ActivityLog


def log_activity(actor, action):
    ActivityLog.objects.create(actor=actor if getattr(actor, "pk", None) else None, action=action[:300])
