from django.urls import path
from .views import fetch_option_chain

urlpatterns = [
    path("chain/", fetch_option_chain, name="option_chain"),
]
