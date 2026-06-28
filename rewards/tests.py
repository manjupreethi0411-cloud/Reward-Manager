from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase
from decimal import Decimal
from datetime import timedelta
from rewards.models import Category, Reward, RewardAuditLog

User = get_user_model()

class RewardManagementTests(APITestCase):

    def setUp(self):
        # Users setup
        self.user1 = User.objects.create_user(
            email='user1@example.com',
            password='StrongPassword123!',
            first_name='User',
            last_name='One'
        )
        self.user2 = User.objects.create_user(
            email='user2@example.com',
            password='StrongPassword123!',
            first_name='User',
            last_name='Two'
        )

        # Authenticate user1
        login_resp = self.client.post(
            reverse('users:token_obtain_pair'),
            {'email': 'user1@example.com', 'password': 'StrongPassword123!'},
            format='json'
        )
        self.access_token = login_resp.data['access']
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.access_token}')

        # Categories are seeded by the migration, fetch them
        self.cat_shopping = Category.objects.get(name='SHOPPING')
        self.cat_food = Category.objects.get(name='FOOD')
        self.cat_travel = Category.objects.get(name='TRAVEL')

        # Create basic rewards for testing lists, filters, sort
        self.reward_active = Reward.objects.create(
            user=self.user1,
            category=self.cat_shopping,
            title='Shopping Reward 1',
            reward_type=Reward.RewardType.COUPON,
            status=Reward.RewardStatus.ACTIVE,
            value=Decimal('25.00'),
            issuer_name='Amazon',
            expiry_date=timezone.now() + timedelta(days=10),
            is_starred=True
        )
        
        self.reward_used = Reward.objects.create(
            user=self.user1,
            category=self.cat_food,
            title='Food Cashback 1',
            reward_type=Reward.RewardType.CASHBACK,
            status=Reward.RewardStatus.USED,
            value=Decimal('5.50'),
            issuer_name='UberEats',
            expiry_date=timezone.now() + timedelta(days=2),
            is_starred=False
        )

        self.reward_expired = Reward.objects.create(
            user=self.user1,
            category=self.cat_travel,
            title='Travel Points 1',
            reward_type=Reward.RewardType.LOYALTY_POINTS,
            status=Reward.RewardStatus.EXPIRED,
            value=Decimal('100.00'),
            issuer_name='Delta Airlines',
            expiry_date=timezone.now() - timedelta(days=1),
            is_starred=False
        )

        # Other user's reward for isolation testing
        self.other_reward = Reward.objects.create(
            user=self.user2,
            category=self.cat_shopping,
            title='Other User Giftcard',
            reward_type=Reward.RewardType.GIFT_CARD,
            status=Reward.RewardStatus.ACTIVE,
            value=Decimal('50.00'),
            issuer_name='Walmart'
        )

        self.rewards_list_url = reverse('rewards:reward-list')

    def test_create_reward_success(self):
        """Test creating a reward manually works and encrypts secrets."""
        data = {
            'category': str(self.cat_shopping.id),
            'title': 'New Gift Card',
            'description': 'Amazon holiday promo',
            'reward_type': 'GIFT_CARD',
            'value': '50.00',
            'code': 'AMZN-SECRET-VOUCHER-123',
            'pin': '9988',
            'issuer_name': 'Amazon',
            'expiry_date': (timezone.now() + timedelta(days=30)).isoformat()
        }
        response = self.client.post(self.rewards_list_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['title'], data['title'])
        self.assertEqual(response.data['code'], data['code']) # Decrypted in response
        self.assertEqual(response.data['pin'], data['pin']) # Decrypted in response

        # Verify DB entry
        new_reward = Reward.objects.get(id=response.data['id'])
        self.assertEqual(new_reward.title, 'New Gift Card')
        # Check database level encryption
        self.assertNotEqual(new_reward.encrypted_code, data['code'])
        self.assertEqual(new_reward.code, data['code'])

        # Verify Audit Log was generated
        audit_log = RewardAuditLog.objects.filter(reward=new_reward).first()
        self.assertIsNotNone(audit_log)
        self.assertEqual(audit_log.action, RewardAuditLog.AuditAction.CREATE)

    def test_update_reward_diff_logging(self):
        """Test patching updates fields and logs diff correctly."""
        url = reverse('rewards:reward-detail', kwargs={'pk': str(self.reward_active.id)})
        data = {
            'title': 'Amazon Prime Exclusive Coupon',
            'value': '30.00',
            'is_starred': False
        }
        response = self.client.patch(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify database fields changed
        self.reward_active.refresh_from_db()
        self.assertEqual(self.reward_active.title, data['title'])
        self.assertEqual(self.reward_active.value, Decimal('30.00'))
        self.assertFalse(self.reward_active.is_starred)

        # Verify Audit Log
        audit_log = RewardAuditLog.objects.filter(
            reward=self.reward_active, 
            action=RewardAuditLog.AuditAction.UPDATE
        ).first()
        self.assertIsNotNone(audit_log)
        self.assertIn('title', audit_log.change_log)
        self.assertIn('value', audit_log.change_log)
        self.assertEqual(audit_log.change_log['value']['old'], '25.00')
        self.assertEqual(audit_log.change_log['value']['new'], '30.00')

    def test_delete_reward_soft(self):
        """Test delete action performs soft-delete and logs it."""
        url = reverse('rewards:reward-detail', kwargs={'pk': str(self.reward_active.id)})
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        # Verify soft-delete: not returned in standard queryset, but exists
        self.assertFalse(Reward.objects.filter(id=self.reward_active.id).exists())
        self.assertTrue(Reward.all_objects.filter(id=self.reward_active.id).exists())
        
        # Verify db status flags
        deleted_item = Reward.all_objects.get(id=self.reward_active.id)
        self.assertTrue(deleted_item.is_deleted)
        self.assertIsNotNone(deleted_item.deleted_at)

        # Verify Audit Log
        audit_log = RewardAuditLog.objects.filter(
            reward=deleted_item, 
            action=RewardAuditLog.AuditAction.DELETE
        ).first()
        self.assertIsNotNone(audit_log)

    def test_mark_reward_used(self):
        """Test mark-used endpoint alters status and logs action."""
        url = reverse('rewards:reward-mark-used', kwargs={'pk': str(self.reward_active.id)})
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'USED')

        # Verify DB
        self.reward_active.refresh_from_db()
        self.assertEqual(self.reward_active.status, Reward.RewardStatus.USED)

        # Audit check
        audit_log = RewardAuditLog.objects.filter(
            reward=self.reward_active,
            action=RewardAuditLog.AuditAction.USE
        ).first()
        self.assertIsNotNone(audit_log)
        self.assertEqual(audit_log.change_log['status']['old'], 'ACTIVE')
        self.assertEqual(audit_log.change_log['status']['new'], 'USED')

        # Double mark-used fails
        response_retry = self.client.post(url)
        self.assertEqual(response_retry.status_code, status.HTTP_400_BAD_REQUEST)

    def test_ownership_isolation(self):
        """Test users cannot access other user's rewards."""
        # Try to retrieve other user's reward details
        url = reverse('rewards:reward-detail', kwargs={'pk': str(self.other_reward.id)})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        # Try to update other user's reward
        response_patch = self.client.patch(url, {'title': 'Hacked Title'}, format='json')
        self.assertEqual(response_patch.status_code, status.HTTP_404_NOT_FOUND)

        # Try to delete other user's reward
        response_delete = self.client.delete(url)
        self.assertEqual(response_delete.status_code, status.HTTP_404_NOT_FOUND)

    def test_list_rewards_and_search(self):
        """Test search filters title and issuer."""
        # Search by issuer (Delta)
        response = self.client.get(self.rewards_list_url, {'search': 'Delta'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['title'], self.reward_expired.title)

        # Search by title (Cashback)
        response = self.client.get(self.rewards_list_url, {'search': 'Cashback'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['issuer_name'], 'UberEats')

    def test_filter_rewards(self):
        """Test filtering by status, category, stars, and expiry dates."""
        # Filter by status USED
        response = self.client.get(self.rewards_list_url, {'status': 'USED'})
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['id'], str(self.reward_used.id))

        # Filter by category SHOPPING
        response = self.client.get(self.rewards_list_url, {'category': str(self.cat_shopping.id)})
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['id'], str(self.reward_active.id))

        # Filter by is_starred
        response = self.client.get(self.rewards_list_url, {'is_starred': 'true'})
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['id'], str(self.reward_active.id))

        # Filter by expiry_before
        five_days_from_now = (timezone.now() + timedelta(days=5)).isoformat()
        response = self.client.get(self.rewards_list_url, {'expiry_before': five_days_from_now})
        # Should return UberEats (expires in 2 days) and Delta (expired in -1 day)
        self.assertEqual(len(response.data['results']), 2)

    def test_sorting_rewards(self):
        """Test sorting rewards by value and expiry_date."""
        # Sort by value ascending (UberEats: 5.50 < Amazon: 25.00 < Delta: 100.00)
        response = self.client.get(self.rewards_list_url, {'ordering': 'value'})
        results = response.data['results']
        self.assertEqual(results[0]['issuer_name'], 'UberEats')
        self.assertEqual(results[1]['issuer_name'], 'Amazon')
        self.assertEqual(results[2]['issuer_name'], 'Delta Airlines')

        # Sort by expiry_date descending (Amazon: +10 days > UberEats: +2 days > Delta: -1 day)
        response = self.client.get(self.rewards_list_url, {'ordering': '-expiry_date'})
        results = response.data['results']
        self.assertEqual(results[0]['issuer_name'], 'Amazon')
        self.assertEqual(results[1]['issuer_name'], 'UberEats')
        self.assertEqual(results[2]['issuer_name'], 'Delta Airlines')

    def test_analytics_endpoint(self):
        """Test retrieving reward analytics."""
        analytics_url = reverse('rewards:reward-analytics')
        response = self.client.get(analytics_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Verify status counts
        self.assertEqual(response.data['total_rewards'], 3)
        self.assertEqual(response.data['active_rewards'], 1)
        self.assertEqual(response.data['used_rewards'], 1)
        self.assertEqual(response.data['expired_rewards'], 1)

        # Verify monthly savings (reward_used has value 5.50)
        monthly_savings = response.data['monthly_savings']
        self.assertGreaterEqual(len(monthly_savings), 1)
        self.assertEqual(monthly_savings[0]['savings'], 5.50)

        # Verify category grouping
        rewards_by_category = response.data['rewards_by_category']
        self.assertGreaterEqual(len(rewards_by_category), 1)
        # Should contain food, shopping, and travel categories
        categories = {item['category_name'] for item in rewards_by_category}
        self.assertIn('Food', categories)
        self.assertIn('Shopping', categories)
        self.assertIn('Travel', categories)

