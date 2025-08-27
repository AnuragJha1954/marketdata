from django.urls import path
from . import views

urlpatterns = [
    path("login/", views.user_login, name="login"),
    path("blank/", views.blank_page, name="blank_page"),
]
