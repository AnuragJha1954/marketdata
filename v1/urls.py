from django.urls import path
from . import views

urlpatterns = [
    path("home/", views.manage_token, name="manage_token"),
]
