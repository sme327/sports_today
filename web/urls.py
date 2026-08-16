from django.urls import path

from web import views

urlpatterns = [
    path("", views.today, name="today"),
    path("fragments/schedule/", views.schedule_fragment, name="schedule-fragment"),
    path("health/", views.health, name="health"),
]
