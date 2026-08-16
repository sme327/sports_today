from django.urls import path

from web import views

urlpatterns = [
    path("", views.today, name="today"),
    path("results/", views.results, name="results"),
    path("performance/", views.performance, name="performance"),
    path("game/<str:league>/<str:game_id>/", views.game, name="game"),
    path("fragments/schedule/", views.schedule_fragment, name="schedule-fragment"),
    path("health/", views.health, name="health"),
]
