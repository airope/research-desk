from django.urls import path

from . import api, views

urlpatterns = [
    path("review/", views.queue, name="queue"),
    path("review/<uuid:pk>/", views.compare, name="compare"),
    path("decisions/<uuid:pk>/withdraw/", views.withdrawal, name="withdraw"),
    path("catalogue/", views.catalogue, name="catalogue"),
    path("catalogue/<uuid:pk>/", views.publication, name="publication"),
    path("imports/", views.imports, name="imports"),
    path("evaluation/", views.evaluation, name="evaluation"),
    path("health/live", views.live, name="health-live"),
    path("health/ready", views.ready, name="health-ready"),
    path("api/v1/candidates", api.CandidateList.as_view()),
    path("api/v1/candidates/<uuid:pk>", api.CandidateDetail.as_view()),
    path("api/v1/candidates/<uuid:pk>/decisions", api.DecisionCreate.as_view()),
    path("api/v1/decisions/<uuid:pk>/withdraw", api.DecisionWithdraw.as_view()),
    path("api/v1/records/<uuid:pk>", api.RecordDetail.as_view()),
    path("api/v1/records/<uuid:pk>/versions", api.RecordVersions.as_view()),
    path("api/v1/publications", api.PublicationList.as_view()),
    path("api/v1/publications/<uuid:pk>", api.PublicationDetail.as_view()),
    path("api/v1/publications/<uuid:pk>/history", api.PublicationHistory.as_view()),
    path("api/v1/imports", api.ImportCreate.as_view()),
    path("api/v1/imports/<uuid:pk>", api.ImportDetail.as_view()),
    path("api/v1/imports/<uuid:pk>/retry", api.ImportRetry.as_view()),
]
