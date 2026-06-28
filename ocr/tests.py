import os
import io
from decimal import Decimal
from unittest.mock import patch, MagicMock
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase
from PIL import Image
from ocr.models import OCRTransaction
from ocr.services import OCRService
from rewards.models import Category, Reward

User = get_user_model()


def create_test_image(filename='test_receipt.jpg', format='JPEG') -> SimpleUploadedFile:
    """Helper that generates an in-memory JPEG image for upload testing."""
    img = Image.new('RGB', (400, 300), color=(255, 255, 255))
    img_io = io.BytesIO()
    img.save(img_io, format=format)
    img_io.seek(0)
    return SimpleUploadedFile(
        filename,
        img_io.read(),
        content_type='image/jpeg'
    )


class OCRServiceTests(APITestCase):
    """Unit tests for the OCR parsing service (isolated, no file I/O)."""

    def setUp(self):
        self.service = OCRService()

    def test_extract_merchant_from_known_brand(self):
        """Should identify known brands in header lines."""
        result = self.service.parse_reward_data(
            "AMAZON GIFT CARD\nValue: $50.00\nCode: AMZN-ABCD-1234\nExpires: 12/31/2026"
        )
        self.assertEqual(result['merchant_name'], 'Amazon')

    def test_extract_value_from_text(self):
        """Should parse monetary amounts correctly."""
        result = self.service.parse_reward_data("Total: $25.50\nCode: ABCD1234EFGH")
        self.assertEqual(result['value'], Decimal('25.50'))

    def test_extract_value_with_currency_in_different_formats(self):
        """Should handle various currency formats."""
        result1 = self.service.parse_reward_data("Amount: 10.00 USD")
        self.assertEqual(result1['value'], Decimal('10.00'))

    def test_extract_code_standard_format(self):
        """Should match standard 12-16 char alphanumeric voucher codes."""
        result = self.service.parse_reward_data(
            "Merchant\nValue: $10.00\nCode: SBUX9876ABCD\nValid till 2027"
        )
        self.assertEqual(result['code'], 'SBUX9876ABCD')

    def test_extract_code_hyphenated_format(self):
        """Should match XXXX-XXXX-XXXX hyphenated format codes."""
        result = self.service.parse_reward_data(
            "Amazon Gift Card\nCode: AMZN-FREE-GIFT\nExp 12/2026"
        )
        self.assertIsNotNone(result['code'])

    def test_extract_expiry_date_slash_format(self):
        """Should parse MM/DD/YYYY expiry dates."""
        result = self.service.parse_reward_data(
            "Gift Card\nExpires: 12/31/2026\nCode: TESTCODE1234"
        )
        self.assertIsNotNone(result['expiry_date'])
        self.assertEqual(result['expiry_date'].year, 2026)
        self.assertEqual(result['expiry_date'].month, 12)
        self.assertEqual(result['expiry_date'].day, 31)

    def test_extract_expiry_date_iso_format(self):
        """Should parse YYYY-MM-DD expiry dates."""
        result = self.service.parse_reward_data(
            "Hotel Reward\nValid thru: 2027-06-15\nCode: HOTEL9988"
        )
        self.assertIsNotNone(result['expiry_date'])
        self.assertEqual(result['expiry_date'].year, 2027)

    def test_unknown_merchant_fallback(self):
        """Should fall back to first line text as issuer name."""
        result = self.service.parse_reward_data(
            "SUPER MARKET COUPON\nTotal $5.00\nCode: MKTCPN5678"
        )
        self.assertIn('SUPER MARKET', result['merchant_name'].upper())

    def test_no_fields_present(self):
        """Should return Nones gracefully when text yields nothing useful."""
        result = self.service.parse_reward_data("random text with no relevant fields")
        self.assertIsNone(result['value'])
        self.assertIsNone(result['expiry_date'])


class OCRAPITests(APITestCase):
    """Integration tests for OCR upload and polling endpoints."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='ocrtest@example.com',
            password='StrongPassword123!',
            first_name='OCR',
            last_name='User'
        )
        login_resp = self.client.post(
            reverse('users:token_obtain_pair'),
            {'email': 'ocrtest@example.com', 'password': 'StrongPassword123!'},
            format='json'
        )
        self.access_token = login_resp.data['access']
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.access_token}')

        self.scan_url = reverse('ocr:ocr_scan')
        self.scan_list_url = reverse('ocr:ocr_scan_list')

    def tearDown(self):
        """Clean up any uploaded media files after each test."""
        for transaction in OCRTransaction.all_objects.filter(user=self.user):
            if transaction.receipt_image and os.path.exists(transaction.receipt_image.path):
                os.remove(transaction.receipt_image.path)

    @patch('ocr.views.process_ocr_receipt_task.delay')
    def test_upload_image_returns_202(self, mock_task):
        """Test valid image upload returns 202 Accepted with transaction ID."""
        mock_task.return_value = None
        image = create_test_image()
        response = self.client.post(self.scan_url, {'receipt_image': image}, format='multipart')

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertIn('id', response.data)
        self.assertEqual(response.data['status'], 'PENDING')

        # Verify Celery task was dispatched
        mock_task.assert_called_once()

    @patch('ocr.views.process_ocr_receipt_task.delay')
    def test_upload_creates_transaction_record(self, mock_task):
        """Test transaction record is created in DB on upload."""
        mock_task.return_value = None
        image = create_test_image()
        response = self.client.post(self.scan_url, {'receipt_image': image}, format='multipart')

        transaction_id = response.data['id']
        self.assertTrue(OCRTransaction.objects.filter(id=transaction_id).exists())

        transaction = OCRTransaction.objects.get(id=transaction_id)
        self.assertEqual(str(transaction.user.id), str(self.user.id))
        self.assertEqual(transaction.status, OCRTransaction.OCRStatus.PENDING)

    def test_upload_fails_for_unsupported_file(self):
        """Test PDF file upload is rejected with 400."""
        pdf_file = SimpleUploadedFile(
            'document.pdf',
            b'%PDF-1.4 fake pdf content',
            content_type='application/pdf'
        )
        response = self.client.post(self.scan_url, {'receipt_image': pdf_file}, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_upload_fails_for_missing_image(self):
        """Test that missing file returns 400."""
        response = self.client.post(self.scan_url, {}, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_upload_requires_authentication(self):
        """Test unauthenticated requests are rejected."""
        self.client.credentials()
        image = create_test_image()
        response = self.client.post(self.scan_url, {'receipt_image': image}, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    @patch('ocr.views.process_ocr_receipt_task.delay')
    def test_poll_transaction_status(self, mock_task):
        """Test polling endpoint returns current transaction status."""
        mock_task.return_value = None
        image = create_test_image()
        upload_resp = self.client.post(self.scan_url, {'receipt_image': image}, format='multipart')
        transaction_id = upload_resp.data['id']

        poll_url = reverse('ocr:ocr_scan_detail', kwargs={'pk': transaction_id})
        response = self.client.get(poll_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], transaction_id)
        self.assertEqual(response.data['status'], 'PENDING')

    @patch('ocr.views.process_ocr_receipt_task.delay')
    def test_list_scan_transactions(self, mock_task):
        """Test listing returns only the current user's transactions."""
        mock_task.return_value = None
        # Create 2 scans for user
        for _ in range(2):
            image = create_test_image()
            self.client.post(self.scan_url, {'receipt_image': image}, format='multipart')

        response = self.client.get(self.scan_list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 2)

    @patch('ocr.views.process_ocr_receipt_task.delay')
    def test_cannot_poll_other_users_transaction(self, mock_task):
        """Test user cannot access another user's OCR transaction."""
        mock_task.return_value = None
        # Create transaction for user1
        image = create_test_image()
        upload_resp = self.client.post(self.scan_url, {'receipt_image': image}, format='multipart')
        transaction_id = upload_resp.data['id']

        # Login as different user
        user2 = User.objects.create_user(
            email='other@example.com',
            password='StrongPassword123!',
            first_name='Other',
            last_name='User'
        )
        login_resp2 = self.client.post(
            reverse('users:token_obtain_pair'),
            {'email': 'other@example.com', 'password': 'StrongPassword123!'},
            format='json'
        )
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {login_resp2.data["access"]}')

        poll_url = reverse('ocr:ocr_scan_detail', kwargs={'pk': transaction_id})
        response = self.client.get(poll_url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class OCRTaskTests(APITestCase):
    """Unit tests for Celery task execution with mocked OCR service."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='tasktest@example.com',
            password='StrongPassword123!',
            first_name='Task',
            last_name='Test'
        )

    @patch('ocr.tasks.OCRService')
    def test_task_completes_and_creates_reward(self, MockOCRService):
        """Test OCR Celery task completes and auto-creates a Reward."""
        from ocr.tasks import process_ocr_receipt_task

        # Build a mock service that returns clean parsed data
        mock_service_instance = MagicMock()
        mock_service_instance.process_image.return_value = (
            "AMAZON GIFT CARD\nValue: $50.00\nCode: AMZN-FREE-GIFT\nExpires: 12/31/2026",
            []
        )
        mock_service_instance.parse_reward_data.return_value = {
            'merchant_name': 'Amazon',
            'code': 'AMZNFREEGIFT',
            'value': Decimal('50.00'),
            'expiry_date': timezone.make_aware(timezone.datetime(2026, 12, 31)),
            'raw_text': 'AMAZON GIFT CARD\nValue: $50.00\nCode: AMZN-FREE-GIFT\nExpires: 12/31/2026'
        }
        MockOCRService.return_value = mock_service_instance

        # Create OCRTransaction with a mock image path
        transaction = OCRTransaction.objects.create(
            user=self.user,
            receipt_image=SimpleUploadedFile('test.jpg', b'fake_image', content_type='image/jpeg'),
            status=OCRTransaction.OCRStatus.PENDING
        )

        # Run task synchronously (CELERY_ALWAYS_EAGER or call directly)
        process_ocr_receipt_task(str(transaction.id))

        transaction.refresh_from_db()
        self.assertEqual(transaction.status, OCRTransaction.OCRStatus.COMPLETED)
        self.assertIsNotNone(transaction.processed_reward)
        self.assertEqual(transaction.processed_reward.issuer_name, 'Amazon')
        self.assertEqual(transaction.processed_reward.value, Decimal('50.00'))
        self.assertEqual(transaction.processed_reward.code, 'AMZNFREEGIFT')

    @patch('ocr.tasks.OCRService')
    def test_task_marks_failed_on_service_error(self, MockOCRService):
        """Test OCR task transitions to FAILED on extraction error."""
        from ocr.tasks import process_ocr_receipt_task

        mock_service_instance = MagicMock()
        mock_service_instance.process_image.side_effect = Exception("GPU Error")
        MockOCRService.return_value = mock_service_instance

        transaction = OCRTransaction.objects.create(
            user=self.user,
            receipt_image=SimpleUploadedFile('test.jpg', b'fake_image', content_type='image/jpeg'),
            status=OCRTransaction.OCRStatus.PENDING
        )

        try:
            process_ocr_receipt_task(str(transaction.id))
        except Exception:
            pass

        transaction.refresh_from_db()
        self.assertEqual(transaction.status, OCRTransaction.OCRStatus.FAILED)
        self.assertIn('OCR extraction failed', transaction.error_message)
