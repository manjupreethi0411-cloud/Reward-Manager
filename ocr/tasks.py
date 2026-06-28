import logging
from celery import shared_task
from django.utils import timezone
from ocr.services import OCRService

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def process_ocr_receipt_task(self, transaction_id: str):
    """
    Async Celery task for OCR-based reward extraction.

    Lifecycle
    ---------
    PENDING → PROCESSING → COMPLETED (Reward created)
                         → FAILED    (error_message populated)

    Retry behaviour
    ---------------
    On image-extraction failures the task retries up to 3 times with a 30-second
    back-off. Parsing and reward-creation failures do NOT retry (they are
    deterministic given the same text) – the transaction is marked FAILED
    immediately so the user can re-upload a clearer image.
    """
    from ocr.models import OCRTransaction
    from rewards.models import Category, Reward

    logger.info(f"[OCR Task] Starting – transaction_id={transaction_id}")

    # ------------------------------------------------------------------
    # 1. Load the transaction
    # ------------------------------------------------------------------
    try:
        transaction = OCRTransaction.objects.select_related('user').get(id=transaction_id)
    except OCRTransaction.DoesNotExist:
        logger.error(f"[OCR Task] OCRTransaction {transaction_id} not found. Aborting.")
        return

    transaction.status = OCRTransaction.OCRStatus.PROCESSING
    transaction.save(update_fields=['status', 'updated_at'])

    service = OCRService()
    image_path = transaction.receipt_image.path

    # ------------------------------------------------------------------
    # 2. Extract text from the image (retriable on failure)
    # ------------------------------------------------------------------
    try:
        raw_text, raw_ocr_data = service.process_image(image_path)
    except Exception as exc:
        logger.error(f"[OCR Task] Image extraction failed: {exc}")
        transaction.status = OCRTransaction.OCRStatus.FAILED
        transaction.error_message = f"OCR extraction failed: {exc}"
        transaction.save(update_fields=['status', 'error_message', 'updated_at'])
        raise self.retry(exc=exc)

    # ------------------------------------------------------------------
    # 3. Parse structured reward fields from the raw text
    # ------------------------------------------------------------------
    try:
        parsed = service.parse_reward_data(raw_text)
    except Exception as exc:
        logger.error(f"[OCR Task] Parsing failed: {exc}")
        transaction.status = OCRTransaction.OCRStatus.FAILED
        transaction.error_message = f"Field parsing failed: {exc}"
        transaction.detected_text = raw_text
        transaction.raw_ocr_data = {"raw_results": str(raw_ocr_data)}
        transaction.save(update_fields=[
            'status', 'error_message', 'detected_text', 'raw_ocr_data', 'updated_at'
        ])
        return

    logger.info(f"[OCR Task] Parsed data: {parsed}")

    # ------------------------------------------------------------------
    # 4. Resolve category (always OTHERS for auto-created OCR rewards)
    # ------------------------------------------------------------------
    category, _ = Category.objects.get_or_create(
        name='OTHERS',
        defaults={'description': 'Miscellaneous rewards'},
    )

    # ------------------------------------------------------------------
    # 5. Validate inferred reward type against model choices
    # ------------------------------------------------------------------
    valid_types = {choice[0] for choice in Reward.RewardType.choices}
    reward_type = parsed.get('reward_type', Reward.RewardType.CASHBACK)
    if reward_type not in valid_types:
        reward_type = Reward.RewardType.CASHBACK

    # ------------------------------------------------------------------
    # 6. Create the Reward record
    # ------------------------------------------------------------------
    try:
        reward = Reward(
            user=transaction.user,
            category=category,
            title=f"{parsed['merchant_name']} Reward (OCR)",
            description=(
                f"Auto-created from uploaded receipt.\n\n"
                f"Detected text (first 500 chars):\n{raw_text[:500]}"
            ),
            reward_type=reward_type,
            status=Reward.RewardStatus.ACTIVE,
            issuer_name=parsed['merchant_name'],
            value=parsed.get('value'),
            expiry_date=parsed.get('expiry_date'),
            issue_date=timezone.now().date(),
        )
        # Use the encrypted property setter so the code is stored securely
        if parsed.get('code'):
            reward.code = parsed['code']
        reward.save()

        # ------------------------------------------------------------------
        # 7. Link the new Reward back to the transaction and mark COMPLETED
        # ------------------------------------------------------------------
        transaction.processed_reward = reward
        transaction.status = OCRTransaction.OCRStatus.COMPLETED
        transaction.detected_text = raw_text
        transaction.raw_ocr_data = {
            "merchant_name": parsed['merchant_name'],
            "reward_type":   reward_type,
            "code":          parsed.get('code'),
            "value":         str(parsed['value']) if parsed.get('value') else None,
            "expiry_date":   str(parsed['expiry_date']) if parsed.get('expiry_date') else None,
        }
        transaction.save(update_fields=[
            'processed_reward', 'status', 'detected_text', 'raw_ocr_data', 'updated_at'
        ])
        logger.info(f"[OCR Task] Reward {reward.id} created for transaction {transaction_id}.")

    except Exception as exc:
        logger.error(f"[OCR Task] Reward creation failed: {exc}")
        transaction.status = OCRTransaction.OCRStatus.FAILED
        transaction.error_message = f"Reward creation failed: {exc}"
        transaction.detected_text = raw_text
        transaction.save(update_fields=[
            'status', 'error_message', 'detected_text', 'updated_at'
        ])
