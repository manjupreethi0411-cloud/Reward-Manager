from rest_framework import serializers
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from reminders.models import Reminder
from rewards.serializers import RewardSerializer


class ReminderSerializer(serializers.ModelSerializer):
    reward_info = RewardSerializer(source='reward', read_only=True)
    reminder_type_display = serializers.CharField(source='get_reminder_type_display', read_only=True)

    class Meta:
        model = Reminder
        fields = [
            'id', 'reward', 'reward_info', 'reminder_time', 'reminder_type',
            'reminder_type_display', 'is_sent', 'sent_at', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'is_sent', 'sent_at', 'created_at', 'updated_at']

    def validate_reminder_time(self, value):
        """Prevent creating reminders in the past."""
        if value <= timezone.now():
            raise serializers.ValidationError(
                _("Reminder time must be in the future.")
            )
        return value

    def validate(self, attrs):
        reward = attrs.get('reward') or (self.instance.reward if self.instance else None)
        reminder_time = attrs.get('reminder_time') or (self.instance.reminder_time if self.instance else None)

        if reward and reminder_time and reward.expiry_date:
            if reminder_time > reward.expiry_date:
                raise serializers.ValidationError({
                    "reminder_time": _("Reminder time cannot be set after the reward's expiry date.")
                })
        return attrs
