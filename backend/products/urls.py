from django.urls import include, path
from rest_framework.routers import SimpleRouter

from . import views

mine = SimpleRouter()
mine.register("mine", views.MyProductViewSet, basename="my-products")
admin_router = SimpleRouter()
admin_router.register("admin", views.AdminProductViewSet, basename="admin-products")

urlpatterns = [
    path("", views.ProductListView.as_view()),
    path("", include(mine.urls)),
    path("", include(admin_router.urls)),
    path("<int:pk>/", views.ProductDetailView.as_view()),
]
