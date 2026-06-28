from rest_framework import serializers
from django.core.validators import FileExtensionValidator
from django.utils.translation import gettext_lazy as _
from ocr.models import OCRTransaction
from rewards.serializers import RewardSerializer


class OCRTransactionCreateSerializer(serializers.ModelSerializer):
    receipt_image = serializers.ImageField(
        validators=[
            FileExtensionValidator(
                allowed_extensions=['jpg', 'jpeg', 'png', 'webp', 'bmp', 'tiff'],
                message=_("Unsupported file type. Upload a JPG, PNG, WEBP, BMP or TIFF image.")
            )
        ]
    )

    class Meta:
        model = OCRTransaction
        fields = ['receipt_image']

    def validate_receipt_image(self, image):
        # 10 MB max upload size
        max_size_mb = 10
        if image.size > max_size_mb * 1024 * 1024:
            raise serializers.ValidationError(
                _(f"Image file too large. Maximum size is {max_size_mb} MB.")
            )
        return image


class OCRTransactionSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    processed_reward = RewardSerializer(read_only=True)

    class Meta:
        model = OCRTransaction
        fields = [
            'id', 'receipt_image', 'status', 'status_display',
            'raw_ocr_data', 'detected_text', 'processed_reward',
            'error_message', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'status', 'raw_ocr_data', 'detected_text', 'processed_reward', 'error_message', 'created_at', 'updated_at']
