from django.urls import path

from web import views

urlpatterns = [
    path("", views.today, name="today"),
    path("results/", views.results, name="results"),
    path("performance/", views.performance, name="performance"),
    path("standings/", views.standings, name="standings"),
    path("trending/", views.trending, name="trending"),
    path("playoffs/", views.playoffs, name="playoffs"),
    path("nfl/", views.nfl_archive, name="nfl-archive"),
    path("nfl/game/<str:game_id>/", views.nfl_matchup, name="nfl-matchup"),
    path("game/<str:league>/<str:game_id>/", views.game, name="game"),
    path("fragments/schedule/", views.schedule_fragment, name="schedule-fragment"),
    path("health/", views.health, name="health"),
]
