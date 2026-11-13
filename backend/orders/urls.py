from django.urls import include, path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("", views.OrderViewSet, basename="order")

urlpatterns = [
    path("documents/<int:pk>/download/", views.OrderDocumentDownloadView.as_view()),
    path("", include(router.urls)),
]
