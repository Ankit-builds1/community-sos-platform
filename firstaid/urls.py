from django.urls import path

from .views import FirstAidAskView

urlpatterns = [
    path("first-aid/ask/", FirstAidAskView.as_view(), name="first-aid-ask"),
]
