from django.urls import path, reverse_lazy
from django.contrib.auth.views import (
    PasswordResetView,
    PasswordResetDoneView,
    PasswordResetConfirmView,
    PasswordResetCompleteView,
)
from frontend.views import (
    LoginPageView,
    LogoutView,
    DashboardView,
    RewardListView,
    RewardDetailView,
    RewardCreateView,
    RewardUpdateView,
    ExpiringRewardsView,
    ProfileView,
    RegisterView,
)
from frontend.forms import StyledPasswordResetForm, StyledSetPasswordForm

app_name = 'frontend'

urlpatterns = [
    # ── Auth ──────────────────────────────────────────────────────────────────
    path('login/',    LoginPageView.as_view(), name='login'),
    path('logout/',   LogoutView.as_view(),    name='logout'),
    path('register/', RegisterView.as_view(),  name='register'),

    # ── Password Reset (Django built-in views, custom templates) ──────────────
    path('password-reset/', PasswordResetView.as_view(
        template_name='web/password_reset.html',
        email_template_name='web/password_reset_email.html',
        subject_template_name='web/password_reset_subject.txt',
        form_class=StyledPasswordResetForm,
        success_url=reverse_lazy('frontend:password_reset_done'),
    ), name='password_reset'),

    path('password-reset/done/', PasswordResetDoneView.as_view(
        template_name='web/password_reset_done.html',
    ), name='password_reset_done'),

    path('password-reset/confirm/<uidb64>/<token>/', PasswordResetConfirmView.as_view(
        template_name='web/password_reset_confirm.html',
        form_class=StyledSetPasswordForm,
        success_url=reverse_lazy('frontend:password_reset_complete'),
    ), name='password_reset_confirm'),

    path('password-reset/complete/', PasswordResetCompleteView.as_view(
        template_name='web/password_reset_complete.html',
    ), name='password_reset_complete'),

    # ── Dashboard ─────────────────────────────────────────────────────────────
    path('dashboard/', DashboardView.as_view(), name='dashboard'),

    # ── Rewards ───────────────────────────────────────────────────────────────
    path('rewards/',                  RewardListView.as_view(),   name='rewards_list'),
    path('rewards/add/',              RewardCreateView.as_view(), name='reward_add'),
    path('rewards/expiring/',         ExpiringRewardsView.as_view(), name='rewards_expiring'),
    path('rewards/<uuid:pk>/',        RewardDetailView.as_view(), name='reward_detail'),
    path('rewards/<uuid:pk>/edit/',   RewardUpdateView.as_view(), name='reward_edit'),

    # ── Profile ───────────────────────────────────────────────────────────────
    path('profile/', ProfileView.as_view(), name='profile'),
]
