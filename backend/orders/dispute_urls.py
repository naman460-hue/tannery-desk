from django.urls import path

from . import views

# Explicit routes: list/create on the collection, retrieve/patch on the item.
urlpatterns = [
    path("", views.DisputeViewSet.as_view({"get": "list", "post": "create"})),
    path("<int:pk>/", views.DisputeViewSet.as_view({"get": "retrieve", "patch": "partial_update"})),
]
