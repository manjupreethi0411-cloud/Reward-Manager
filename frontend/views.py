"""
Frontend views — Django Template–based web UI for Reward Management App.
Uses session-based auth (login_required) while keeping REST API (JWT) intact.
"""
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash, get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.contrib import messages
from django.db.models import Count, Sum, Q
from django.db.models.functions import TruncMonth
from django.utils import timezone
from django.urls import reverse_lazy
from django.shortcuts import redirect, get_object_or_404
from django.views import View
from django.views.generic import (
    TemplateView, ListView, DetailView,
    CreateView, UpdateView,
)
from django.http import JsonResponse

from rewards.models import Reward, Category, RewardAuditLog
from users.models import NotificationPreference
from frontend.forms import (
    LoginForm, RewardForm,
    ProfileForm, NotificationPreferenceForm, ChangePasswordForm,
    RegisterForm,
)

import datetime

User = get_user_model()


# ──────────────────────────────────────────────────────────────────────────────
# Auth Views
# ──────────────────────────────────────────────────────────────────────────────

class LoginPageView(View):
    """Renders login page and handles credential submission."""
    template_name = 'web/login.html'

    def get(self, request):
        if request.user.is_authenticated:
            return redirect('frontend:dashboard')
        form = LoginForm(request)
        return self._render(request, form)

    def post(self, request):
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            next_url = request.GET.get('next', reverse_lazy('frontend:dashboard'))
            return redirect(next_url)
        return self._render(request, form)

    def _render(self, request, form):
        from django.shortcuts import render
        return render(request, self.template_name, {'form': form})


class LogoutView(LoginRequiredMixin, View):
    """Logs the user out and redirects to login."""
    def post(self, request):
        logout(request)
        messages.success(request, 'You have been logged out successfully.')
        return redirect('frontend:login')


# ──────────────────────────────────────────────────────────────────────────────
# Register
# ──────────────────────────────────────────────────────────────────────────────

class RegisterView(View):
    """Renders registration form and handles new user account creation."""
    template_name = 'web/register.html'

    def get(self, request):
        if request.user.is_authenticated:
            return redirect('frontend:dashboard')
        form = RegisterForm()
        return self._render(request, form)

    def post(self, request):
        form = RegisterForm(request.POST)
        if form.is_valid():
            User.objects.create_user(
                email=form.cleaned_data['email'],
                password=form.cleaned_data['password1'],
                first_name=form.cleaned_data['first_name'],
                last_name=form.cleaned_data['last_name'],
            )
            messages.success(
                request,
                '🎉 Account created successfully! Please sign in with your new credentials.'
            )
            return redirect('frontend:login')
        return self._render(request, form)

    def _render(self, request, form):
        from django.shortcuts import render
        return render(request, self.template_name, {
            'form': form,
            'page_title': 'Create Account',
        })


# ──────────────────────────────────────────────────────────────────────────────
# Dashboard
# ──────────────────────────────────────────────────────────────────────────────

class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'web/dashboard.html'
    login_url = reverse_lazy('frontend:login')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        qs = Reward.objects.filter(user=user)

        # Stats
        now = timezone.now()
        ctx['total'] = qs.count()
        ctx['active'] = qs.filter(status=Reward.RewardStatus.ACTIVE).count()
        ctx['used'] = qs.filter(status=Reward.RewardStatus.USED).count()
        ctx['expired'] = qs.filter(status=Reward.RewardStatus.EXPIRED).count()

        # Expiring soon (next 7 days, active only)
        soon = now + datetime.timedelta(days=7)
        ctx['expiring_soon'] = qs.filter(
            status=Reward.RewardStatus.ACTIVE,
            expiry_date__gte=now,
            expiry_date__lte=soon,
        ).count()

        # Starred rewards
        ctx['starred'] = qs.filter(is_starred=True, status=Reward.RewardStatus.ACTIVE)[:5]

        # Recent rewards
        ctx['recent_rewards'] = qs.select_related('category').order_by('-created_at')[:6]

        # Monthly savings (last 6 months)
        six_months_ago = now - datetime.timedelta(days=180)
        monthly_savings = (
            qs.filter(status=Reward.RewardStatus.USED, value__isnull=False,
                      created_at__gte=six_months_ago)
            .annotate(month=TruncMonth('created_at'))
            .values('month')
            .annotate(savings=Sum('value'))
            .order_by('month')
        )
        ctx['monthly_savings'] = [
            {'month': e['month'].strftime('%b %Y'), 'savings': float(e['savings'] or 0)}
            for e in monthly_savings if e['month']
        ]

        # By category
        ctx['by_category'] = (
            qs.values('category__name')
            .annotate(count=Count('id'), total=Sum('value'))
            .order_by('-count')
        )

        ctx['page_title'] = 'Dashboard'
        return ctx


# ──────────────────────────────────────────────────────────────────────────────
# Rewards List
# ──────────────────────────────────────────────────────────────────────────────

class RewardListView(LoginRequiredMixin, ListView):
    template_name = 'web/rewards/list.html'
    context_object_name = 'rewards'
    paginate_by = 12
    login_url = reverse_lazy('frontend:login')

    def get_queryset(self):
        qs = Reward.objects.filter(user=self.request.user).select_related('category')

        # Filters from GET params
        status_filter = self.request.GET.get('status', '')
        reward_type = self.request.GET.get('reward_type', '')
        category_id = self.request.GET.get('category', '')
        starred = self.request.GET.get('starred', '')
        search = self.request.GET.get('q', '').strip()

        if status_filter:
            qs = qs.filter(status=status_filter)
        if reward_type:
            qs = qs.filter(reward_type=reward_type)
        if category_id:
            qs = qs.filter(category__id=category_id)
        if starred == '1':
            qs = qs.filter(is_starred=True)
        if search:
            qs = qs.filter(
                Q(title__icontains=search) |
                Q(issuer_name__icontains=search) |
                Q(description__icontains=search)
            )

        ordering = self.request.GET.get('order', '-created_at')
        allowed_orderings = ['created_at', '-created_at', 'expiry_date', '-expiry_date', 'value', '-value']
        if ordering in allowed_orderings:
            qs = qs.order_by(ordering)

        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['categories'] = Category.objects.all()
        ctx['reward_types'] = Reward.RewardType.choices
        ctx['status_choices'] = Reward.RewardStatus.choices
        ctx['current_filters'] = {
            'status': self.request.GET.get('status', ''),
            'reward_type': self.request.GET.get('reward_type', ''),
            'category': self.request.GET.get('category', ''),
            'starred': self.request.GET.get('starred', ''),
            'q': self.request.GET.get('q', ''),
            'order': self.request.GET.get('order', '-created_at'),
        }
        ctx['page_title'] = 'My Rewards'
        return ctx


# ──────────────────────────────────────────────────────────────────────────────
# Reward Detail
# ──────────────────────────────────────────────────────────────────────────────

class RewardDetailView(LoginRequiredMixin, DetailView):
    template_name = 'web/rewards/detail.html'
    context_object_name = 'reward'
    login_url = reverse_lazy('frontend:login')

    def get_queryset(self):
        return Reward.objects.filter(user=self.request.user).select_related('category')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        reward = self.object
        ctx['audit_logs'] = RewardAuditLog.objects.filter(reward=reward).select_related('user')[:10]
        ctx['page_title'] = f'{reward.issuer_name} — {reward.title}'
        return ctx

    def post(self, request, *args, **kwargs):
        """Handle mark-as-used action."""
        reward = self.get_object()
        action = request.POST.get('action')
        if action == 'mark_used' and reward.status == Reward.RewardStatus.ACTIVE:
            old_status = reward.status
            reward.status = Reward.RewardStatus.USED
            reward.save(update_fields=['status'])
            RewardAuditLog.log_action(
                reward=reward, user=request.user,
                action=RewardAuditLog.AuditAction.USE,
                change_log={'status': {'old': old_status, 'new': reward.status}},
                request=request
            )
            messages.success(request, f'"{reward.title}" marked as used.')
        elif action == 'delete':
            RewardAuditLog.log_action(
                reward=reward, user=request.user,
                action=RewardAuditLog.AuditAction.DELETE,
                change_log={'status': {'old': reward.status, 'new': 'DELETED'}},
                request=request
            )
            reward.delete()
            messages.success(request, 'Reward deleted successfully.')
            return redirect('frontend:rewards_list')
        return redirect('frontend:reward_detail', pk=reward.pk)


# ──────────────────────────────────────────────────────────────────────────────
# Create Reward
# ──────────────────────────────────────────────────────────────────────────────

class RewardCreateView(LoginRequiredMixin, CreateView):
    template_name = 'web/rewards/form.html'
    form_class = RewardForm
    login_url = reverse_lazy('frontend:login')

    def get_success_url(self):
        return reverse_lazy('frontend:reward_detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        form.instance.user = self.request.user
        response = super().form_valid(form)
        RewardAuditLog.log_action(
            reward=self.object, user=self.request.user,
            action=RewardAuditLog.AuditAction.CREATE,
            change_log={'status': {'new': self.object.status}},
            request=self.request
        )
        messages.success(self.request, f'Reward "{self.object.title}" created successfully!')
        return response

    def form_invalid(self, form):
        messages.error(self.request, 'Please fix the errors below.')
        return super().form_invalid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['form_title'] = 'Add New Reward'
        ctx['submit_label'] = 'Create Reward'
        ctx['page_title'] = 'Add Reward'
        return ctx


# ──────────────────────────────────────────────────────────────────────────────
# Edit Reward
# ──────────────────────────────────────────────────────────────────────────────

class RewardUpdateView(LoginRequiredMixin, UpdateView):
    template_name = 'web/rewards/form.html'
    form_class = RewardForm
    login_url = reverse_lazy('frontend:login')

    def get_queryset(self):
        return Reward.objects.filter(user=self.request.user)

    def get_success_url(self):
        return reverse_lazy('frontend:reward_detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        # Capture pre-save values for audit log
        original = Reward.objects.get(pk=self.object.pk)
        old_values = {f: getattr(original, f) for f in form.changed_data if hasattr(original, f)}

        response = super().form_valid(form)

        change_log = {}
        for field in form.changed_data:
            old_val = old_values.get(field)
            new_val = getattr(self.object, field, None)
            if str(old_val) != str(new_val):
                change_log[field] = {'old': str(old_val), 'new': str(new_val)}

        if change_log:
            RewardAuditLog.log_action(
                reward=self.object, user=self.request.user,
                action=RewardAuditLog.AuditAction.UPDATE,
                change_log=change_log,
                request=self.request
            )
        messages.success(self.request, f'Reward "{self.object.title}" updated successfully!')
        return response

    def form_invalid(self, form):
        messages.error(self.request, 'Please fix the errors below.')
        return super().form_invalid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['form_title'] = f'Edit Reward — {self.object.title}'
        ctx['submit_label'] = 'Save Changes'
        ctx['page_title'] = 'Edit Reward'
        ctx['is_edit'] = True
        return ctx


# ──────────────────────────────────────────────────────────────────────────────
# Expiring Rewards
# ──────────────────────────────────────────────────────────────────────────────

class ExpiringRewardsView(LoginRequiredMixin, ListView):
    template_name = 'web/rewards/expiring.html'
    context_object_name = 'rewards'
    login_url = reverse_lazy('frontend:login')

    def get_queryset(self):
        now = timezone.now()
        days = int(self.request.GET.get('days', 30))
        cutoff = now + datetime.timedelta(days=days)
        return (
            Reward.objects.filter(
                user=self.request.user,
                status=Reward.RewardStatus.ACTIVE,
                expiry_date__gte=now,
                expiry_date__lte=cutoff,
            )
            .select_related('category')
            .order_by('expiry_date')
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        now = timezone.now()
        user = self.request.user
        ctx['days'] = int(self.request.GET.get('days', 30))
        ctx['page_title'] = 'Expiring Rewards'
        # Passed as a list so templates don't need the |split filter
        ctx['expiry_day_options'] = [7, 14, 30, 60, 90]

        # Already expired (not yet acknowledged)
        ctx['already_expired'] = (
            Reward.objects.filter(
                user=user,
                status=Reward.RewardStatus.EXPIRED,
            )
            .select_related('category')
            .order_by('-expiry_date')[:10]
        )
        return ctx


# ──────────────────────────────────────────────────────────────────────────────
# Profile
# ──────────────────────────────────────────────────────────────────────────────

class ProfileView(LoginRequiredMixin, View):
    template_name = 'web/profile.html'
    login_url = reverse_lazy('frontend:login')

    def get(self, request):
        profile_form = ProfileForm(instance=request.user)
        try:
            pref = request.user.notification_preference
        except NotificationPreference.DoesNotExist:
            pref = NotificationPreference.objects.create(user=request.user)
        pref_form = NotificationPreferenceForm(instance=pref)
        pw_form = ChangePasswordForm()
        return self._render(request, profile_form, pref_form, pw_form)

    def post(self, request):
        action = request.POST.get('action', '')
        try:
            pref = request.user.notification_preference
        except NotificationPreference.DoesNotExist:
            pref = NotificationPreference.objects.create(user=request.user)

        if action == 'update_profile':
            profile_form = ProfileForm(request.POST, instance=request.user)
            pref_form = NotificationPreferenceForm(instance=pref)
            pw_form = ChangePasswordForm()
            if profile_form.is_valid():
                profile_form.save()
                messages.success(request, 'Profile updated successfully.')
                return redirect('frontend:profile')
            else:
                messages.error(request, 'Please fix the errors below.')

        elif action == 'update_notifications':
            profile_form = ProfileForm(instance=request.user)
            pref_form = NotificationPreferenceForm(request.POST, instance=pref)
            pw_form = ChangePasswordForm()
            if pref_form.is_valid():
                pref_form.save()
                messages.success(request, 'Notification preferences updated.')
                return redirect('frontend:profile')
            else:
                messages.error(request, 'Please fix the errors below.')

        elif action == 'change_password':
            profile_form = ProfileForm(instance=request.user)
            pref_form = NotificationPreferenceForm(instance=pref)
            pw_form = ChangePasswordForm(request.POST)
            if pw_form.is_valid():
                old_pw = pw_form.cleaned_data['old_password']
                new_pw = pw_form.cleaned_data['new_password']
                if not request.user.check_password(old_pw):
                    pw_form.add_error('old_password', 'Current password is incorrect.')
                else:
                    try:
                        validate_password(new_pw, request.user)
                        request.user.set_password(new_pw)
                        request.user.save()
                        update_session_auth_hash(request, request.user)
                        messages.success(request, 'Password changed successfully.')
                        return redirect('frontend:profile')
                    except ValidationError as e:
                        pw_form.add_error('new_password', list(e.messages))
                messages.error(request, 'Please fix the errors below.')
            else:
                messages.error(request, 'Please fix the errors below.')
        else:
            return redirect('frontend:profile')

        return self._render(request, profile_form, pref_form, pw_form)

    def _render(self, request, profile_form, pref_form, pw_form):
        from django.shortcuts import render
        total_rewards = Reward.objects.filter(user=request.user).count()
        active_rewards = Reward.objects.filter(user=request.user, status=Reward.RewardStatus.ACTIVE).count()
        return render(request, self.template_name, {
            'profile_form': profile_form,
            'pref_form': pref_form,
            'pw_form': pw_form,
            'total_rewards': total_rewards,
            'active_rewards': active_rewards,
            'page_title': 'My Profile',
        })
