from django.urls import path

from . import views

urlpatterns = [
    path("", views.PaymentListView.as_view()),
    path("create/", views.CreatePaymentView.as_view()),
    path("verify/", views.VerifyPaymentView.as_view()),
    path("failed/", views.ReportFailureView.as_view()),
    path("webhook/", views.RazorpayWebhookView.as_view()),
    path("<int:pk>/", views.PaymentDetailView.as_view()),
    path("<int:pk>/sandbox/", views.SandboxPayView.as_view()),
]
