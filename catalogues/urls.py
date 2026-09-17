from django.urls import path

from . import views

app_name = "catalogues"
urlpatterns = [
    path("workspaces/", views.home, name="home"),
    path("workspaces/example.csv", views.example, name="example"),
    path("workspaces/new/", views.new, name="new"),
    path("workspaces/<uuid:pk>/", views.detail, name="detail"),
    path("workspaces/<uuid:pk>/selection/", views.selection, name="selection"),
    path("workspaces/previews/<uuid:pk>/", views.preview, name="preview"),
    path("workspaces/entries/<uuid:pk>/", views.entry, name="entry"),
    path("workspaces/<uuid:pk>/export/", views.export, name="export"),
]
