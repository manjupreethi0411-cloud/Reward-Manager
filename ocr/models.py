from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from core.models import BaseModel
from rewards.models import Reward

class OCRTransaction(BaseModel):
    class OCRStatus(models.TextChoices):
        PENDING = 'PENDING', _('Pending')
        PROCESSING = 'PROCESSING', _('Processing')
        COMPLETED = 'COMPLETED', _('Completed')
        FAILED = 'FAILED', _('Failed')

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='ocr_transactions',
        db_index=True
    )
    receipt_image = models.ImageField(
        upload_to='receipts/%Y/%m/%d/',
        help_text=_("Uploaded image of the receipt or voucher.")
    )
    status = models.CharField(
        max_length=20,
        choices=OCRStatus.choices,
        default=OCRStatus.PENDING,
        db_index=True
    )
    raw_ocr_data = models.JSONField(
        null=True,
        blank=True,
        help_text=_("Raw response JSON from the OCR engine.")
    )
    detected_text = models.TextField(
        null=True,
        blank=True,
        help_text=_("Extracted plain text lines.")
    )
    processed_reward = models.OneToOneField(
        Reward,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='ocr_transaction',
        help_text=_("The Reward object generated from this transaction.")
    )
    error_message = models.TextField(
        null=True,
        blank=True,
        help_text=_("Errors logged if the OCR extraction fails.")
    )

    class Meta:
        verbose_name = _('OCR Transaction')
        verbose_name_plural = _('OCR Transactions')
        ordering = ['-created_at']

    def __str__(self):
        return f"OCR {self.id} ({self.status}) for {self.user.email}"
