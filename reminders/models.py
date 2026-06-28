from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from core.models import BaseModel
from rewards.models import Reward


class Reminder(BaseModel):
    class ReminderType(models.TextChoices):
        EMAIL = 'EMAIL', _('Email')
        SMS = 'SMS', _('SMS')
        PUSH = 'PUSH', _('Push Notification')
        IN_APP = 'IN_APP', _('In-App')

    class OffsetDays(models.IntegerChoices):
        ONE_DAY = 1, _('1 Day Before')
        THREE_DAYS = 3, _('3 Days Before')
        SEVEN_DAYS = 7, _('7 Days Before')

    reward = models.ForeignKey(
        Reward,
        on_delete=models.CASCADE,
        related_name='reminders',
        db_index=True
    )
    reminder_time = models.DateTimeField(db_index=True)
    reminder_type = models.CharField(
        max_length=20,
        choices=ReminderType.choices,
        default=ReminderType.EMAIL
    )
    offset_days = models.IntegerField(
        choices=OffsetDays.choices,
        null=True,
        blank=True,
        help_text=_("Days before expiry this reminder is scheduled for (auto-created reminders).")
    )
    is_sent = models.BooleanField(default=False, db_index=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _('Reminder')
        verbose_name_plural = _('Reminders')
        ordering = ['reminder_time']
        indexes = [
            models.Index(fields=['is_sent', 'reminder_time']),
        ]
        # Prevent duplicate reminders for the same offset on the same reward
        constraints = [
            models.UniqueConstraint(
                fields=['reward', 'offset_days', 'reminder_type'],
                condition=models.Q(is_deleted=False, offset_days__isnull=False),
                name='unique_active_offset_reminder'
            )
        ]

    def __str__(self):
        return f"Reminder for '{self.reward.title}' at {self.reminder_time}"

    def clean(self):
        """Validate reminder dates."""
        super().clean()
        if self.reminder_time and self.reward:
            if self.reward.expiry_date and self.reminder_time > self.reward.expiry_date:
                raise ValidationError(_("Reminder time cannot be after the reward's expiry date."))
            if not self.pk and self.reminder_time < timezone.now():
                raise ValidationError(_("Reminder time cannot be set in the past."))

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)


class Notification(BaseModel):
    """
    In-App notification record shown to users in the notification feed.
    Created whenever a reminder is triggered (Email or In-App type).
    """
    class NotificationType(models.TextChoices):
        EXPIRY_REMINDER = 'EXPIRY_REMINDER', _('Expiry Reminder')
        REWARD_CREATED = 'REWARD_CREATED', _('Reward Created')
        REWARD_USED = 'REWARD_USED', _('Reward Used')
        SYSTEM = 'SYSTEM', _('System')

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications',
        db_index=True
    )
    reminder = models.ForeignKey(
        Reminder,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='notifications'
    )
    title = models.CharField(max_length=200)
    body = models.TextField()
    notification_type = models.CharField(
        max_length=30,
        choices=NotificationType.choices,
        default=NotificationType.EXPIRY_REMINDER,
        db_index=True
    )
    is_read = models.BooleanField(default=False, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _('Notification')
        verbose_name_plural = _('Notifications')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'is_read']),
        ]

    def __str__(self):
        return f"{self.title} → {self.user.email}"

    def mark_read(self):
        """Mark this notification as read."""
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=['is_read', 'read_at'])
