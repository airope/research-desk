from django.urls import path

from . import views

app_name = "research"
urlpatterns = [
    path("", views.home, name="home"),
    path("research/<uuid:pk>/", views.detail, name="detail"),
    path("research/<uuid:pk>/versions/<int:index>/", views.version, name="version"),
    path("research/<uuid:pk>/status/", views.status, name="status"),
    path("research/<uuid:pk>/action/", views.action, name="action"),
    path("research/<uuid:pk>/export/", views.export, name="export"),
]
