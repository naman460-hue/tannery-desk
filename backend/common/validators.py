"""Upload validation: allow-list of extensions, size limit, and a check that the content matches the extension."""
import os
import re

from django.conf import settings
from django.core.exceptions import ValidationError

IMAGE_EXT = {"jpg", "jpeg", "png", "webp"}
DOC_EXT = {"pdf", "doc", "docx", "xls", "xlsx", "csv", "txt"}
DOCUMENT_EXT = DOC_EXT | IMAGE_EXT | {"dxf"}
TEXT_EXT = {"csv", "txt", "dxf"}
OLE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
SIGNATURES = {
    "pdf": (b"%PDF",),
    "png": (b"\x89PNG\r\n\x1a\n",),
    "jpg": (b"\xff\xd8\xff",),
    "jpeg": (b"\xff\xd8\xff",),
    "doc": (OLE,), "xls": (OLE,),
    "docx": (b"PK\x03\x04",), "xlsx": (b"PK\x03\x04",),
}
EXECUTABLE_STARTS = (b"MZ", b"\x7fELF", b"#!", b"<?php", b"<script", b"<html", b"<svg")


def clean_filename(name, limit=120):
    base = os.path.basename(name or "file").replace("\\", "/").split("/")[-1]
    base = re.sub(r"[^\w.\- ]", "_", base).strip(" .") or "file"
    return base[-limit:]


def _check(upload, allowed_ext):
    ext = os.path.splitext(upload.name or "")[1].lower().lstrip(".")
    if ext not in allowed_ext:
        raise ValidationError("This file type is not allowed. Allowed types: " + ", ".join(sorted(allowed_ext)) + ".")
    limit_mb = settings.MAX_UPLOAD_MB
    if upload.size > limit_mb * 1024 * 1024:
        raise ValidationError(f"The file is too large. The maximum size is {limit_mb} MB.")
    if upload.size == 0:
        raise ValidationError("The file is empty.")
    upload.seek(0)
    head = upload.read(8192)
    upload.seek(0)
    if head.startswith(EXECUTABLE_STARTS):
        raise ValidationError("This file type is not allowed.")
    if ext in SIGNATURES:
        if not any(head.startswith(sig) for sig in SIGNATURES[ext]):
            raise ValidationError("The file content does not match its type.")
    elif ext == "webp":
        if not (head[:4] == b"RIFF" and head[8:12] == b"WEBP"):
            raise ValidationError("The file content does not match its type.")
    elif ext in TEXT_EXT and b"\x00" in head:
        raise ValidationError("The file content does not match its type.")
    return ext


def validate_document_upload(upload):
    ext = _check(upload, DOCUMENT_EXT)
    if ext in IMAGE_EXT:
        _verify_image(upload)


def validate_image_upload(upload):
    _check(upload, IMAGE_EXT)
    _verify_image(upload)


def _verify_image(upload):
    from PIL import Image

    try:
        upload.seek(0)
        Image.open(upload).verify()
    except Exception:
        raise ValidationError("This image could not be read. Please upload a valid JPG, PNG or WebP image.")
    finally:
        upload.seek(0)
