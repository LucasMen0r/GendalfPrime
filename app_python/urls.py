from django.urls import path
from . import view

app_name = "app_python"

urlpatterns = [
    path("", view.index, name="index"),
]