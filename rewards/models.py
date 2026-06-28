import uuid
import logging
from decimal import Decimal
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from cryptography.fernet import Fernet
from core.models import BaseModel

logger = logging.getLogger(__name__)

def encrypt_field(value: str) -> str:
    """Encrypts a string value using the application key."""
    if not value:
        return None
    try:
        f = Fernet(settings.ENCRYPTION_KEY.encode())
        return f.encrypt(value.encode()).decode()
    except Exception as e:
        logger.error(f"Field encryption failed: {e}")
        raise ValidationError(_("Secure field encryption failed."))

def decrypt_field(encrypted_value: str) -> str:
    """Decrypts a string value using the application key."""
    if not encrypted_value:
        return None
    try:
        f = Fernet(settings.ENCRYPTION_KEY.encode())
        return f.decrypt(encrypted_value.encode()).decode()
    except Exception as e:
        logger.error(f"Field decryption failed: {e}")
        return "[DECRYPTION_ERROR]"


class Category(BaseModel):
    class CategoryName(models.TextChoices):
        TRAVEL = 'TRAVEL', _('Travel')
        FOOD = 'FOOD', _('Food')
        SHOPPING = 'SHOPPING', _('Shopping')
        CASHBACK = 'CASHBACK', _('Cashback')
        ENTERTAINMENT = 'ENTERTAINMENT', _('Entertainment')
        BILLS = 'BILLS', _('Bills')
        OTHERS = 'OTHERS', _('Others')

    name = models.CharField(
        max_length=50,
        choices=CategoryName.choices,
        unique=True,
        db_index=True
    )
    description = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name = _('Category')
        verbose_name_plural = _('Categories')
        constraints = [
            models.UniqueConstraint(
                fields=['name'],
                condition=models.Q(is_deleted=False),
                name='unique_active_category_name'
            )
        ]

    def __str__(self):
        return self.get_name_display()


class Reward(BaseModel):
    class RewardType(models.TextChoices):
        CASHBACK = 'CASHBACK', _('Cashback')
        COUPON = 'COUPON', _('Coupon')
        GIFT_CARD = 'GIFT_CARD', _('Gift Card')
        LOYALTY_POINTS = 'LOYALTY_POINTS', _('Loyalty Points')
        PAYMENT_APP_REWARD = 'PAYMENT_APP_REWARD', _('Payment App Reward')

    class RewardStatus(models.TextChoices):
        ACTIVE = 'ACTIVE', _('Active')
        USED = 'USED', _('Used')
        EXPIRED = 'EXPIRED', _('Expired')

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='rewards',
        db_index=True
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name='rewards',
        db_index=True
    )
    title = models.CharField(max_length=150)
    description = models.TextField(blank=True, null=True)
    reward_type = models.CharField(
        max_length=30,
        choices=RewardType.choices,
        db_index=True
    )
    status = models.CharField(
        max_length=20,
        choices=RewardStatus.choices,
        default=RewardStatus.ACTIVE,
        db_index=True
    )
    value = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    
    # Encrypted fields
    encrypted_code = models.CharField(max_length=500, blank=True, null=True, db_column='code')
    encrypted_pin = models.CharField(max_length=500, blank=True, null=True, db_column='pin')
    
    url = models.URLField(blank=True, null=True)
    loyalty_program_name = models.CharField(max_length=100, blank=True, null=True)
    issuer_name = models.CharField(max_length=100, db_index=True)
    issue_date = models.DateField(blank=True, null=True)
    expiry_date = models.DateTimeField(blank=True, null=True, db_index=True)
    is_starred = models.BooleanField(default=False)

    class Meta:
        verbose_name = _('Reward')
        verbose_name_plural = _('Rewards')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['expiry_date', 'status']),
        ]

    def __str__(self):
        return f"{self.issuer_name} - {self.title}"

    # Properties to handle automatic encryption/decryption transparently
    @property
    def code(self) -> str:
        return decrypt_field(self.encrypted_code)

    @code.setter
    def code(self, value: str):
        self.encrypted_code = encrypt_field(value)

    @property
    def pin(self) -> str:
        return decrypt_field(self.encrypted_pin)

    @pin.setter
    def pin(self, value: str):
        self.encrypted_pin = encrypt_field(value)

    def clean(self):
        """Validate models constraints."""
        super().clean()
        if self.expiry_date and self.issue_date:
            # Convert issue_date to datetime for comparison
            issue_datetime = timezone.make_aware(
                timezone.datetime.combine(self.issue_date, timezone.datetime.min.time())
            )
            if self.expiry_date < issue_datetime:
                raise ValidationError(_("Expiry date cannot be before the issue date."))

    def save(self, *args, **kwargs):
        self.clean()
        # Auto-update status to EXPIRED if it has passed expiry date
        if self.expiry_date and self.expiry_date <= timezone.now() and self.status == self.RewardStatus.ACTIVE:
            self.status = self.RewardStatus.EXPIRED
        super().save(*args, **kwargs)

    @property
    def is_expired(self) -> bool:
        """Helper checking if reward is past its expiration date."""
        if self.expiry_date:
            return timezone.now() >= self.expiry_date
        return False


class RewardAuditLog(models.Model):
    class AuditAction(models.TextChoices):
        CREATE = 'CREATE', _('Create')
        UPDATE = 'UPDATE', _('Update')
        DELETE = 'DELETE', _('Delete')
        USE = 'USE', _('Use')
        RESTORE = 'RESTORE', _('Restore')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reward = models.ForeignKey(
        Reward,
        on_delete=models.SET_NULL,
        null=True,
        related_name='audit_logs'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='reward_audit_logs'
    )
    action = models.CharField(max_length=20, choices=AuditAction.choices)
    change_log = models.JSONField(
        help_text=_("JSON body tracking updated fields and before/after values.")
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = _('Reward Audit Log')
        verbose_name_plural = _('Reward Audit Logs')
        ordering = ['-timestamp']

    @classmethod
    def log_action(cls, reward, user, action, change_log, request=None):
        """Helper to create audit log records capturing request client details."""
        ip_address = None
        user_agent = None
        if request:
            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            if x_forwarded_for:
                ip_address = x_forwarded_for.split(',')[0].strip()
            else:
                ip_address = request.META.get('REMOTE_ADDR')
            user_agent = request.META.get('HTTP_USER_AGENT')
        
        return cls.objects.create(
            reward=reward,
            user=user,
            action=action,
            change_log=change_log,
            ip_address=ip_address,
            user_agent=user_agent
        )
