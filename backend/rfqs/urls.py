from django.urls import include, path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("", views.RFQViewSet, basename="rfq")

urlpatterns = [
    path("attachments/<int:pk>/download/", views.AttachmentDownloadView.as_view()),
    path("", include(router.urls)),
]
