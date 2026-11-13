import os
import re
import uuid

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible


def private_storage():
    """Files here are never served by a public URL; they are only reachable through permission-checked API downloads."""
    return FileSystemStorage(location=str(settings.PRIVATE_MEDIA_ROOT))


@deconstructible
class RandomPath:
    """upload_to helper: stores files under a random name so user-supplied names never touch the filesystem."""

    def __init__(self, prefix):
        self.prefix = prefix

    def __call__(self, instance, filename):
        ext = os.path.splitext(filename or "")[1].lower()
        if not re.fullmatch(r"\.[a-z0-9]{1,8}", ext):
            ext = ""
        return f"{self.prefix}/{uuid.uuid4().hex}{ext}"
