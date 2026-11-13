from django.urls import path

from . import views

urlpatterns = [
    path("meta/options/", views.OptionsView.as_view()),
    path("dashboard/", views.DashboardView.as_view()),
    path("search/", views.SearchView.as_view()),
    path("admin/reports/", views.AdminReportsView.as_view()),
]
