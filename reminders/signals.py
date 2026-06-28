from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from datetime import timedelta
from rewards.models import Reward
from reminders.models import Reminder

@receiver(post_save, sender=Reward)
def handle_reward_reminders(sender, instance, created, **kwargs):
    """
    Signal receiver to auto-schedule reminders for 7, 3, and 1 days before expiry
    whenever a Reward is created or updated.
    If the expiry date changes, updates or recreates unsent reminders.
    """
    if not instance.expiry_date or instance.is_deleted or instance.status != Reward.RewardStatus.ACTIVE:
        # If no active/valid expiry date, soft-delete existing unsent reminders
        instance.reminders.filter(is_sent=False).delete()
        return

    now = timezone.now()
    offsets = [7, 3, 1]
    
    # Get user notification preference or default to EMAIL
    try:
        pref = instance.user.notification_preference
        reminder_type = (
            Reminder.ReminderType.EMAIL if pref.email_enabled
            else Reminder.ReminderType.IN_APP
        )
    except Exception:
        reminder_type = Reminder.ReminderType.EMAIL

    # Query existing unsent reminders for this reward
    existing_unsent = instance.reminders.filter(is_sent=False)
    
    for offset in offsets:
        reminder_time = instance.expiry_date - timedelta(days=offset)
        if reminder_time > now:
            # Create or update the reminder for this offset day
            Reminder.objects.update_or_create(
                reward=instance,
                offset_days=offset,
                reminder_type=reminder_type,
                is_deleted=False,
                defaults={
                    'reminder_time': reminder_time,
                    'is_sent': False
                }
            )
        else:
            # If the calculated reminder time is in the past, delete any unsent reminder for this offset
            existing_unsent.filter(offset_days=offset).delete()
            
    # Clean up any unsent reminders that are not in our target offsets
    existing_unsent.exclude(offset_days__in=offsets).delete()
