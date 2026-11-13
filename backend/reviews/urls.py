from django.urls import path

from . import views

urlpatterns = [
    path("", views.ReviewListView.as_view()),
    path("create/", views.ReviewCreateView.as_view()),
]
