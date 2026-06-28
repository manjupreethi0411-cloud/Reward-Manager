from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase
from rewards.models import Category, Reward
from reminders.models import Reminder

User = get_user_model()


class ReminderAPITests(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            email='reminder_user@example.com',
            password='StrongPassword123!',
            first_name='Reminder',
            last_name='User'
        )
        self.other_user = User.objects.create_user(
            email='other@example.com',
            password='StrongPassword123!',
            first_name='Other',
            last_name='User'
        )

        # Authenticate as main user
        login_resp = self.client.post(
            reverse('users:token_obtain_pair'),
            {'email': 'reminder_user@example.com', 'password': 'StrongPassword123!'},
            format='json'
        )
        self.access_token = login_resp.data['access']
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.access_token}')

        self.category = Category.objects.get(name='SHOPPING')
        self.future_expiry = timezone.now() + timedelta(days=30)

        # User's reward
        self.reward = Reward.objects.create(
            user=self.user,
            category=self.category,
            title='Test Coupon',
            reward_type=Reward.RewardType.COUPON,
            issuer_name='TestShop',
            expiry_date=self.future_expiry
        )

        # Other user's reward
        self.other_reward = Reward.objects.create(
            user=self.other_user,
            category=self.category,
            title='Other Coupon',
            reward_type=Reward.RewardType.COUPON,
            issuer_name='OtherShop',
            expiry_date=self.future_expiry
        )

        self.reminders_url = reverse('reminders:reminder-list')

    def test_create_reminder_success(self):
        """Test creating a valid future reminder."""
        reminder_time = timezone.now() + timedelta(days=7)
        data = {
            'reward': str(self.reward.id),
            'reminder_time': reminder_time.isoformat(),
            'reminder_type': 'EMAIL',
        }
        response = self.client.post(self.reminders_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertFalse(response.data['is_sent'])
        self.assertEqual(response.data['reminder_type'], 'EMAIL')

    def test_create_reminder_in_past_fails(self):
        """Test reminder time in the past is rejected."""
        data = {
            'reward': str(self.reward.id),
            'reminder_time': (timezone.now() - timedelta(hours=1)).isoformat(),
            'reminder_type': 'EMAIL',
        }
        response = self.client.post(self.reminders_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('reminder_time', response.data)

    def test_create_reminder_after_reward_expiry_fails(self):
        """Test reminder time after reward expiry date is rejected."""
        data = {
            'reward': str(self.reward.id),
            'reminder_time': (self.future_expiry + timedelta(days=1)).isoformat(),
            'reminder_type': 'EMAIL',
        }
        response = self.client.post(self.reminders_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_reminder_for_other_user_reward_fails(self):
        """Test creating a reminder for another user's reward is forbidden."""
        data = {
            'reward': str(self.other_reward.id),
            'reminder_time': (timezone.now() + timedelta(days=5)).isoformat(),
            'reminder_type': 'EMAIL',
        }
        response = self.client.post(self.reminders_url, data, format='json')
        # Should be 403 (PermissionDenied) since reward lookup is user-scoped
        self.assertIn(response.status_code, [status.HTTP_403_FORBIDDEN, status.HTTP_400_BAD_REQUEST])

    def test_list_reminders_only_own(self):
        """Test list returns only current user's reminders."""
        # Create reminder for user
        Reminder.objects.create(
            reward=self.reward,
            reminder_time=timezone.now() + timedelta(days=5),
            reminder_type=Reminder.ReminderType.EMAIL
        )
        # Create reminder for other user
        Reminder.objects.create(
            reward=self.other_reward,
            reminder_time=timezone.now() + timedelta(days=5),
            reminder_type=Reminder.ReminderType.EMAIL
        )

        response = self.client.get(self.reminders_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Only own reminder visible
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(str(response.data['results'][0]['reward']), str(self.reward.id))

    def test_filter_reminders_by_is_sent(self):
        """Test filtering reminders by sent status."""
        Reminder.objects.create(
            reward=self.reward,
            reminder_time=timezone.now() + timedelta(days=3),
            reminder_type=Reminder.ReminderType.EMAIL,
            is_sent=True,
            sent_at=timezone.now()
        )
        Reminder.objects.create(
            reward=self.reward,
            reminder_time=timezone.now() + timedelta(days=7),
            reminder_type=Reminder.ReminderType.PUSH,
            is_sent=False
        )

        response = self.client.get(self.reminders_url, {'is_sent': 'false'})
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['reminder_type'], 'PUSH')

    def test_filter_reminders_by_reward_id(self):
        """Test filtering by reward_id."""
        reward2 = Reward.objects.create(
            user=self.user,
            category=self.category,
            title='Second Coupon',
            reward_type=Reward.RewardType.COUPON,
            issuer_name='Shop2',
            expiry_date=self.future_expiry
        )
        Reminder.objects.create(
            reward=self.reward,
            reminder_time=timezone.now() + timedelta(days=5),
        )
        Reminder.objects.create(
            reward=reward2,
            reminder_time=timezone.now() + timedelta(days=5),
        )

        response = self.client.get(self.reminders_url, {'reward_id': str(self.reward.id)})
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(str(response.data['results'][0]['reward']), str(self.reward.id))

    def test_update_reminder_time(self):
        """Test rescheduling a reminder."""
        reminder = Reminder.objects.create(
            reward=self.reward,
            reminder_time=timezone.now() + timedelta(days=5),
        )
        url = reverse('reminders:reminder-detail', kwargs={'pk': str(reminder.id)})
        new_time = timezone.now() + timedelta(days=10)
        response = self.client.patch(url, {'reminder_time': new_time.isoformat()}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        reminder.refresh_from_db()
        self.assertGreater(reminder.reminder_time, timezone.now() + timedelta(days=9))

    def test_delete_reminder(self):
        """Test soft-deleting a reminder."""
        reminder = Reminder.objects.create(
            reward=self.reward,
            reminder_time=timezone.now() + timedelta(days=5),
        )
        url = reverse('reminders:reminder-detail', kwargs={'pk': str(reminder.id)})
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        # Soft delete: not in default manager
        self.assertFalse(Reminder.objects.filter(id=reminder.id).exists())
        # But exists in all_objects
        self.assertTrue(Reminder.all_objects.filter(id=reminder.id).exists())


class ReminderTaskTests(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            email='tasktest@example.com',
            password='StrongPassword123!',
            first_name='Task',
            last_name='User'
        )
        self.category = Category.objects.get(name='FOOD')
        self.reward = Reward.objects.create(
            user=self.user,
            category=self.category,
            title='Expiring Food Reward',
            reward_type=Reward.RewardType.CASHBACK,
            issuer_name='DoorDash',
            value=Decimal('8.00'),
            expiry_date=timezone.now() + timedelta(days=2)
        )

    @patch('reminders.tasks.send_reminder_notification_task.delay')
    def test_beat_task_dispatches_due_reminders(self, mock_dispatch):
        """Test that the Beat task dispatches due reminders via delay()."""
        from reminders.tasks import check_and_send_due_reminders_task

        # Create a past-due reminder
        Reminder.objects.create(
            reward=self.reward,
            reminder_time=timezone.now() - timedelta(minutes=5),  # Overdue
            is_sent=False
        )

        check_and_send_due_reminders_task()
        mock_dispatch.assert_called_once()

    @patch('reminders.tasks.send_reminder_notification_task.delay')
    def test_beat_task_skips_sent_reminders(self, mock_dispatch):
        """Test Beat task does not re-dispatch already sent reminders."""
        from reminders.tasks import check_and_send_due_reminders_task

        Reminder.objects.create(
            reward=self.reward,
            reminder_time=timezone.now() - timedelta(minutes=5),
            is_sent=True,  # Already sent
            sent_at=timezone.now()
        )

        check_and_send_due_reminders_task()
        mock_dispatch.assert_not_called()

    def test_auto_create_expiry_reminders_creates_for_soon_expiring(self):
        """Test auto task creates reminders for rewards expiring in 3 days."""
        from reminders.tasks import auto_create_expiry_reminders_task

        self.assertEqual(self.reward.reminders.count(), 0)
        auto_create_expiry_reminders_task()
        self.assertEqual(self.reward.reminders.count(), 1)

    def test_auto_create_expiry_reminders_skips_if_reminder_exists(self):
        """Test auto task does not create duplicate unsent reminders."""
        from reminders.tasks import auto_create_expiry_reminders_task

        # Pre-existing unsent reminder
        Reminder.objects.create(
            reward=self.reward,
            reminder_time=timezone.now() + timedelta(hours=10),
            is_sent=False
        )
        auto_create_expiry_reminders_task()
        # Should still be only 1
        self.assertEqual(self.reward.reminders.count(), 1)
