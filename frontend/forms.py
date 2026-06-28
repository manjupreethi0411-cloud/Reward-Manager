from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, PasswordResetForm, SetPasswordForm
from django.contrib.auth.password_validation import validate_password as dj_validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rewards.models import Reward, Category
from users.models import NotificationPreference

User = get_user_model()


class LoginForm(AuthenticationForm):
    """Custom login form using email as username field."""
    username = forms.EmailField(
        label='Email Address',
        widget=forms.EmailInput(attrs={
            'class': 'form-input',
            'placeholder': 'you@example.com',
            'autocomplete': 'email',
            'id': 'id_email',
        })
    )
    password = forms.CharField(
        label='Password',
        widget=forms.PasswordInput(attrs={
            'class': 'form-input',
            'placeholder': '••••••••',
            'autocomplete': 'current-password',
            'id': 'id_password',
        })
    )


class RewardForm(forms.ModelForm):
    """Form for creating and editing Reward instances."""

    code = forms.CharField(
        required=False,
        label='Reward Code',
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'e.g. SAVE20',
        })
    )
    pin = forms.CharField(
        required=False,
        label='PIN',
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'Optional PIN',
        })
    )
    expiry_date = forms.DateTimeField(
        required=False,
        widget=forms.DateTimeInput(attrs={
            'class': 'form-input',
            'type': 'datetime-local',
        }),
        input_formats=['%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M'],
    )
    issue_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-input',
            'type': 'date',
        })
    )

    class Meta:
        model = Reward
        fields = [
            'title', 'category', 'reward_type', 'status',
            'issuer_name', 'description', 'value',
            'code', 'pin', 'url',
            'loyalty_program_name', 'issue_date', 'expiry_date',
            'is_starred',
        ]
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'e.g. Amazon ₹200 Gift Card',
            }),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'reward_type': forms.Select(attrs={'class': 'form-select'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'issuer_name': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'e.g. Amazon, Swiggy',
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-input',
                'rows': 3,
                'placeholder': 'Optional notes about this reward…',
            }),
            'value': forms.NumberInput(attrs={
                'class': 'form-input',
                'placeholder': '0.00',
                'step': '0.01',
                'min': '0',
            }),
            'url': forms.URLInput(attrs={
                'class': 'form-input',
                'placeholder': 'https://',
            }),
            'loyalty_program_name': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'e.g. Club Vistara',
            }),
            'is_starred': forms.CheckboxInput(attrs={'class': 'form-checkbox'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Populate code and pin from model properties on edit
        if self.instance and self.instance.pk:
            self.fields['code'].initial = self.instance.code
            self.fields['pin'].initial = self.instance.pin
        # Only show non-deleted categories
        self.fields['category'].queryset = Category.objects.all()

    def save(self, commit=True):
        instance = super().save(commit=False)
        # Assign encrypted properties via model setters
        code_val = self.cleaned_data.get('code')
        pin_val = self.cleaned_data.get('pin')
        if code_val is not None:
            instance.code = code_val
        if pin_val is not None:
            instance.pin = pin_val
        if commit:
            instance.save()
        return instance


class ProfileForm(forms.ModelForm):
    """Form for updating user profile (name only; email is read-only)."""

    class Meta:
        model = User
        fields = ['first_name', 'last_name']
        widgets = {
            'first_name': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'First name',
            }),
            'last_name': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'Last name',
            }),
        }


class NotificationPreferenceForm(forms.ModelForm):
    """Form for updating notification preferences."""

    class Meta:
        model = NotificationPreference
        fields = ['email_enabled', 'sms_enabled', 'push_enabled']
        widgets = {
            'email_enabled': forms.CheckboxInput(attrs={'class': 'form-checkbox'}),
            'sms_enabled': forms.CheckboxInput(attrs={'class': 'form-checkbox'}),
            'push_enabled': forms.CheckboxInput(attrs={'class': 'form-checkbox'}),
        }


class ChangePasswordForm(forms.Form):
    """Form to change the current user's password."""

    old_password = forms.CharField(
        label='Current Password',
        widget=forms.PasswordInput(attrs={
            'class': 'form-input',
            'placeholder': '••••••••',
            'autocomplete': 'current-password',
        })
    )
    new_password = forms.CharField(
        label='New Password',
        widget=forms.PasswordInput(attrs={
            'class': 'form-input',
            'placeholder': '••••••••',
            'autocomplete': 'new-password',
        })
    )
    confirm_password = forms.CharField(
        label='Confirm New Password',
        widget=forms.PasswordInput(attrs={
            'class': 'form-input',
            'placeholder': '••••••••',
            'autocomplete': 'new-password',
        })
    )

    def clean(self):
        cleaned_data = super().clean()
        new_password = cleaned_data.get('new_password')
        confirm_password = cleaned_data.get('confirm_password')
        if new_password and confirm_password and new_password != confirm_password:
            self.add_error('confirm_password', 'Passwords do not match.')
        return cleaned_data


class RegisterForm(forms.Form):
    """Form for new user self-registration."""

    first_name = forms.CharField(
        label='First Name',
        max_length=150,
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'First name',
            'autocomplete': 'given-name',
        })
    )
    last_name = forms.CharField(
        label='Last Name',
        max_length=150,
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'Last name',
            'autocomplete': 'family-name',
        })
    )
    email = forms.EmailField(
        label='Email Address',
        widget=forms.EmailInput(attrs={
            'class': 'form-input',
            'placeholder': 'you@example.com',
            'autocomplete': 'email',
        })
    )
    password1 = forms.CharField(
        label='Password',
        widget=forms.PasswordInput(attrs={
            'class': 'form-input',
            'placeholder': '••••••••',
            'autocomplete': 'new-password',
        })
    )
    password2 = forms.CharField(
        label='Confirm Password',
        widget=forms.PasswordInput(attrs={
            'class': 'form-input',
            'placeholder': '••••••••',
            'autocomplete': 'new-password',
        })
    )

    def clean_email(self):
        email = self.cleaned_data.get('email', '').lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(
                'An account with this email already exists. '
                'Please sign in or use a different email.'
            )
        return email

    def clean_password1(self):
        password1 = self.cleaned_data.get('password1')
        if password1:
            try:
                dj_validate_password(password1)
            except DjangoValidationError as e:
                raise forms.ValidationError(list(e.messages))
        return password1

    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get('password1')
        p2 = cleaned_data.get('password2')
        if p1 and p2 and p1 != p2:
            self.add_error('password2', 'Passwords do not match.')
        return cleaned_data


class StyledPasswordResetForm(PasswordResetForm):
    """Django's PasswordResetForm with project CSS classes applied."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['email'].widget.attrs.update({
            'class': 'form-input',
            'placeholder': 'you@example.com',
            'autocomplete': 'email',
        })


class StyledSetPasswordForm(SetPasswordForm):
    """Django's SetPasswordForm with project CSS classes applied."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['new_password1'].widget.attrs.update({
            'class': 'form-input',
            'placeholder': '••••••••',
            'autocomplete': 'new-password',
        })
        self.fields['new_password2'].widget.attrs.update({
            'class': 'form-input',
            'placeholder': '••••••••',
            'autocomplete': 'new-password',
        })
