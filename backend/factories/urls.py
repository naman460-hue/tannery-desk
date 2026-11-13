from django.urls import path

from . import views

urlpatterns = [
    path("", views.FactoryListView.as_view()),
    path("me/", views.MyFactoryView.as_view()),
    path("me/documents/", views.MyDocumentsView.as_view()),
    path("me/documents/<int:pk>/", views.MyDocumentDeleteView.as_view()),
    path("documents/<int:pk>/download/", views.DocumentDownloadView.as_view()),
    path("admin/", views.AdminFactoryListView.as_view()),
    path("admin/<int:pk>/verification/", views.AdminFactoryVerificationView.as_view()),
    path("<int:pk>/", views.FactoryDetailView.as_view()),
]
