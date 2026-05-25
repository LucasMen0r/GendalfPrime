from django.urls import path
from . import view

app_name = "app_python"

urlpatterns = [
    path("", view.index, name="index"),
    path("ad/", view.admin_index, name="admin_index"),
    path("exemplos/adicionar/", view.adicionar_exemplo, name="adicionar_exemplo"),
    path("exemplos/remover/", view.remover_exemplo_view, name="remover_exemplo"),
    path("manual/upload/", view.upload_manual_view, name="upload_manual"),
]