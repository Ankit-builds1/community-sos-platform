from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path("", views.landing, name="landing"),
    path("board/", views.board, name="board"),
    path("login/", auth_views.LoginView.as_view(
        template_name="dashboard/login.html",
        extra_context={"demo_accounts": views.DEMO_ACCOUNTS},
        redirect_authenticated_user=True), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("signup/", views.signup, name="signup"),
    path("start/", views.onboard, name="onboard"),
    path("sandbox/", views.sandbox_start, name="sandbox_start"),
    path("sandbox/as/<str:role>/", views.sandbox_switch, name="sandbox_switch"),
    path("society/new/", views.register_society, name="register_society"),
    path("join/", views.join, name="join"),
    path("join/<str:code>/", views.join, name="join_code"),
    path("manage/", views.manage, name="manage"),
    path("manage/requests/<int:pk>/<str:verdict>/", views.decide, name="decide"),
    path("circle/", views.circle, name="circle"),
    path("invite/<str:token>/", views.invite, name="invite"),
]
