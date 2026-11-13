from django.http import FileResponse, Http404


def file_response(field_file, filename):
    if not field_file:
        raise Http404("File not found")
    try:
        handle = field_file.open("rb")
    except FileNotFoundError:
        raise Http404("File not found")
    response = FileResponse(handle, as_attachment=True, filename=filename or "download")
    response["X-Content-Type-Options"] = "nosniff"
    return response
