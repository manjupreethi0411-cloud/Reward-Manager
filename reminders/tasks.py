import logging
from celery import shared_task
from django.utils import timezone
from django.db import transaction

logger = logging.getLogger(__name__)


@shared_task
def send_reminder_notification_task(reminder_id: str):
    """
    Celery task to dispatch a single due reminder notification.
    Marks the reminder as sent after successful delivery.
    """
    from reminders.models import Reminder
    from reminders.models import Notification

    try:
        reminder = Reminder.objects.select_related('reward', 'reward__user').get(id=reminder_id)
    except Reminder.DoesNotExist:
        logger.error(f"[Reminder] ID {reminder_id} not found.")
        return

    if reminder.is_sent:
        logger.info(f"[Reminder] {reminder_id} already sent. Skipping.")
        return

    user = reminder.reward.user
    reward = reminder.reward

    try:
        if reminder.reminder_type == Reminder.ReminderType.EMAIL:
            _send_email_notification(user, reward, reminder)

        # Create an in-app notification record regardless of type so it is visible in the feed
        Notification.objects.create(
            user=user,
            reminder=reminder,
            title=f"⏰ Expiry Reminder: {reward.title}",
            body=(
                f"Your reward \"{reward.title}\" from {reward.issuer_name} "
                f"expires on {reward.expiry_date.strftime('%d %b %Y') if reward.expiry_date else 'N/A'}."
            ),
            notification_type=Notification.NotificationType.EXPIRY_REMINDER
        )

        # Mark sent
        reminder.is_sent = True
        reminder.sent_at = timezone.now()
        reminder.save(update_fields=['is_sent', 'sent_at'])
        logger.info(f"[Reminder] {reminder_id} sent successfully.")

    except Exception as exc:
        logger.error(f"[Reminder] Failed to send {reminder_id}: {exc}")
        raise


def _send_email_notification(user, reward, reminder):
    """Send email reminder using Django's send_mail."""
    from django.core.mail import send_mail
    from django.conf import settings

    expiry_str = reward.expiry_date.strftime('%d %b %Y') if reward.expiry_date else 'N/A'
    subject = f"⏰ Reminder: {reward.title} expires on {expiry_str}"
    message = (
        f"Hi {user.first_name},\n\n"
        f"This is a reminder that your reward \"{reward.title}\" from {reward.issuer_name} "
        f"is expiring on {expiry_str}.\n\n"
        f"{'Reward value: ' + str(reward.value) if reward.value else ''}\n\n"
        f"Make sure to use it before it expires!\n\n"
        f"— Reward Manager"
    )
    send_mail(
        subject=subject,
        message=message,
        from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@rewardmanager.com'),
        recipient_list=[user.email],
        fail_silently=False
    )


@shared_task
def check_and_send_due_reminders_task():
    """
    Periodic Celery Beat task that:
      1. Queries all unsent, due reminders using SELECT FOR UPDATE (skip_locked)
      2. Dispatches individual notification tasks for each
    """
    from reminders.models import Reminder

    now = timezone.now()
    dispatched = 0

    try:
        with transaction.atomic():
            due_reminders = Reminder.objects.select_for_update(
                skip_locked=True
            ).filter(
                reminder_time__lte=now,
                is_sent=False,
                is_deleted=False
            )

            for reminder in due_reminders:
                send_reminder_notification_task.delay(str(reminder.id))
                dispatched += 1

        logger.info(f"[Beat] Dispatched {dispatched} reminder tasks.")

    except Exception as exc:
        logger.error(f"[Beat] check_and_send_due_reminders_task failed: {exc}")
        raise


@shared_task
def auto_create_expiry_reminders_task():
    """
    Periodic Celery Beat task that auto-creates reminders for active
    rewards expiring soon, at 7, 3, and 1 day offsets.
    """
    from rewards.models import Reward
    from reminders.models import Reminder
    from datetime import timedelta

    now = timezone.now()
    # Find all active rewards with an expiry date in the future
    active_rewards = Reward.objects.filter(
        expiry_date__gt=now,
        status=Reward.RewardStatus.ACTIVE
    ).prefetch_related('reminders')

    created_count = 0
    offsets = [7, 3, 1]

    for reward in active_rewards:
        # Skip if the reward already has active unsent reminders to prevent duplicates
        if reward.reminders.filter(is_sent=False, is_deleted=False).exists():
            continue

        try:
            pref = reward.user.notification_preference
            reminder_type = (
                Reminder.ReminderType.EMAIL if pref.email_enabled
                else Reminder.ReminderType.IN_APP
            )
        except Exception:
            reminder_type = Reminder.ReminderType.EMAIL

        for offset in offsets:
            reminder_time = reward.expiry_date - timedelta(days=offset)
            # Only create reminder if the calculated reminder time is in the future.
            if reminder_time > now:
                Reminder.objects.create(
                    reward=reward,
                    reminder_time=reminder_time,
                    reminder_type=reminder_type,
                    offset_days=offset
                )
                created_count += 1

    logger.info(f"[Beat] Auto-created {created_count} expiry reminders for 7, 3, and 1 day offsets.")
