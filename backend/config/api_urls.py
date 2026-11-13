from django.urls import include, path

urlpatterns = [
    path("auth/", include("accounts.urls")),
    path("factories/", include("factories.urls")),
    path("products/", include("products.urls")),
    path("rfqs/", include("rfqs.urls")),
    path("quotations/", include("rfqs.quotation_urls")),
    path("orders/", include("orders.urls")),
    path("disputes/", include("orders.dispute_urls")),
    path("payments/", include("payments.urls")),
    path("notifications/", include("notifications.urls")),
    path("messages/", include("messaging.urls")),
    path("reviews/", include("reviews.urls")),
    path("", include("core.urls")),
]
