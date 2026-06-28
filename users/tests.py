from django.urls import reverse
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase
from users.models import NotificationPreference

User = get_user_model()

class UserAuthenticationTests(APITestCase):

    def setUp(self):
        self.register_url = reverse('users:register')
        self.login_url = reverse('users:token_obtain_pair')
        self.refresh_url = reverse('users:token_refresh')
        self.logout_url = reverse('users:logout')
        self.profile_url = reverse('users:me')
        self.password_url = reverse('users:change_password')

        # Test user setup
        self.user_data = {
            'email': 'john.doe@example.com',
            'password': 'StrongPassword123!',
            'first_name': 'John',
            'last_name': 'Doe'
        }
        self.user = User.objects.create_user(**self.user_data)
        
    def test_user_registration_success(self):
        """Test registration creates user and preferences."""
        data = {
            'email': 'new.user@example.com',
            'password': 'SecurePassWord987!',
            'first_name': 'New',
            'last_name': 'User'
        }
        response = self.client.post(self.register_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['email'], data['email'])
        
        # Verify db user was created
        created_user = User.objects.get(email=data['email'])
        self.assertIsNotNone(created_user)
        # Verify notification preferences were auto-created
        self.assertTrue(NotificationPreference.objects.filter(user=created_user).exists())

    def test_user_registration_fails_duplicate_email(self):
        """Test registration fails for duplicate email."""
        data = {
            'email': self.user_data['email'],
            'password': 'DifferentPassword123!',
            'first_name': 'Jane',
            'last_name': 'Doe'
        }
        response = self.client.post(self.register_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('email', response.data)

    def test_user_registration_fails_weak_password(self):
        """Test registration fails with weak password."""
        data = {
            'email': 'weak@example.com',
            'password': '123',
            'first_name': 'Weak',
            'last_name': 'Pass'
        }
        response = self.client.post(self.register_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('password', response.data)

    def test_user_login_success(self):
        """Test correct credentials return tokens."""
        data = {
            'email': self.user_data['email'],
            'password': self.user_data['password']
        }
        response = self.client.post(self.login_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)

    def test_user_login_fails_wrong_password(self):
        """Test incorrect password login attempt fails."""
        data = {
            'email': self.user_data['email'],
            'password': 'WrongPassword123'
        }
        response = self.client.post(self.login_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_token_refresh(self):
        """Test refresh token retrieves new access token."""
        login_data = {
            'email': self.user_data['email'],
            'password': self.user_data['password']
        }
        login_resp = self.client.post(self.login_url, login_data, format='json')
        refresh_token = login_resp.data['refresh']

        response = self.client.post(self.refresh_url, {'refresh': refresh_token}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)

    def test_user_logout(self):
        """Test logout blacklists refresh token."""
        login_data = {
            'email': self.user_data['email'],
            'password': self.user_data['password']
        }
        login_resp = self.client.post(self.login_url, login_data, format='json')
        refresh_token = login_resp.data['refresh']
        access_token = login_resp.data['access']

        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access_token}')
        response = self.client.post(self.logout_url, {'refresh': refresh_token}, format='json')
        self.assertEqual(response.status_code, status.HTTP_205_RESET_CONTENT)

        # Try to refresh again, should fail because it was blacklisted
        refresh_resp = self.client.post(self.refresh_url, {'refresh': refresh_token}, format='json')
        self.assertEqual(refresh_resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_get_user_profile_authenticated(self):
        """Test profile access for authenticated user."""
        login_data = {
            'email': self.user_data['email'],
            'password': self.user_data['password']
        }
        login_resp = self.client.post(self.login_url, login_data, format='json')
        access_token = login_resp.data['access']

        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access_token}')
        response = self.client.get(self.profile_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['email'], self.user_data['email'])
        self.assertIn('notification_preference', response.data)

    def test_get_user_profile_unauthenticated(self):
        """Test profile access blocked if unauthenticated."""
        response = self.client.get(self.profile_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_update_user_profile(self):
        """Test updating profile fields and nested notification flags."""
        login_data = {
            'email': self.user_data['email'],
            'password': self.user_data['password']
        }
        login_resp = self.client.post(self.login_url, login_data, format='json')
        access_token = login_resp.data['access']

        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access_token}')
        update_data = {
            'first_name': 'Johnny',
            'last_name': 'Smith',
            'notification_preference': {
                'email_enabled': False,
                'sms_enabled': True,
                'push_enabled': False
            }
        }
        response = self.client.put(self.profile_url, update_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['first_name'], update_data['first_name'])
        self.assertEqual(response.data['last_name'], update_data['last_name'])
        self.assertEqual(
            response.data['notification_preference']['email_enabled'],
            update_data['notification_preference']['email_enabled']
        )
        self.assertEqual(
            response.data['notification_preference']['sms_enabled'],
            update_data['notification_preference']['sms_enabled']
        )

        # Verify db changes
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'Johnny')
        self.assertFalse(self.user.notification_preference.email_enabled)
        self.assertTrue(self.user.notification_preference.sms_enabled)

    def test_change_password_success(self):
        """Test password change with valid credentials."""
        login_data = {
            'email': self.user_data['email'],
            'password': self.user_data['password']
        }
        login_resp = self.client.post(self.login_url, login_data, format='json')
        access_token = login_resp.data['access']

        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access_token}')
        data = {
            'old_password': self.user_data['password'],
            'new_password': 'NewSecurePassword543!'
        }
        response = self.client.post(self.password_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Try to login with the new password
        login_new = {
            'email': self.user_data['email'],
            'password': 'NewSecurePassword543!'
        }
        login_resp = self.client.post(self.login_url, login_new, format='json')
        self.assertEqual(login_resp.status_code, status.HTTP_200_OK)

    def test_change_password_fails_incorrect_old_password(self):
        """Test password change fails with wrong old password."""
        login_data = {
            'email': self.user_data['email'],
            'password': self.user_data['password']
        }
        login_resp = self.client.post(self.login_url, login_data, format='json')
        access_token = login_resp.data['access']

        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access_token}')
        data = {
            'old_password': 'WrongPassword123!',
            'new_password': 'NewSecurePassword543!'
        }
        response = self.client.post(self.password_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
