from django.contrib.auth import views as auth_views
from django.urls import path

from .views import DEMO_ACCOUNTS, board

urlpatterns = [
    path("", board, name="board"),
    path("login/", auth_views.LoginView.as_view(
        template_name="dashboard/login.html",
        extra_context={"demo_accounts": DEMO_ACCOUNTS},
        redirect_authenticated_user=True), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
]
