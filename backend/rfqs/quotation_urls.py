from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("", views.QuotationViewSet, basename="quotation")
urlpatterns = router.urls
