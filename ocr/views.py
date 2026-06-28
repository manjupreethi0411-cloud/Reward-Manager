import logging
from rest_framework import generics, permissions, status, parsers
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiResponse
from ocr.models import OCRTransaction
from ocr.serializers import OCRTransactionCreateSerializer, OCRTransactionSerializer
from ocr.tasks import process_ocr_receipt_task

logger = logging.getLogger(__name__)


class OCRScanView(generics.CreateAPIView):
    """
    Upload a receipt, coupon, or gift card image.
    Processing is handled asynchronously via Celery.
    Returns an OCR transaction ID to poll for results.
    """
    serializer_class = OCRTransactionCreateSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [parsers.MultiPartParser, parsers.FormParser]

    @extend_schema(
        summary="Upload image for OCR scanning",
        description=(
            "Upload a receipt, coupon or gift card image. "
            "Triggers async OCR text extraction and reward auto-creation. "
            "Poll `/api/v1/ocr/scans/{id}/` with the returned transaction ID."
        ),
        responses={
            202: OCRTransactionSerializer,
            400: OpenApiResponse(description="Validation error (file too large / unsupported type)")
        }
    )
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Create the transaction record
        transaction = OCRTransaction.objects.create(
            user=request.user,
            receipt_image=serializer.validated_data['receipt_image'],
            status=OCRTransaction.OCRStatus.PENDING
        )

        logger.info(f"[OCR] Transaction {transaction.id} created for user {request.user.email}.")

        # Dispatch async Celery task
        try:
            process_ocr_receipt_task.delay(str(transaction.id))
        except Exception as exc:
            logger.error(f"[OCR] Failed to dispatch task for {transaction.id}: {exc}")
            transaction.status = OCRTransaction.OCRStatus.FAILED
            transaction.error_message = "Failed to queue OCR processing task. Please try again."
            transaction.save(update_fields=['status', 'error_message'])

        response_serializer = OCRTransactionSerializer(transaction)
        return Response(response_serializer.data, status=status.HTTP_202_ACCEPTED)


class OCRScanListView(generics.ListAPIView):
    """
    List all OCR scan transactions for the authenticated user.
    """
    serializer_class = OCRTransactionSerializer
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(summary="List OCR scan history")
    def get_queryset(self):
        return OCRTransaction.objects.filter(user=self.request.user).order_by('-created_at')


class OCRScanDetailView(generics.RetrieveAPIView):
    """
    Retrieve the status and result of a specific OCR scan transaction.
    Poll this endpoint after uploading an image to check if OCR completed.
    """
    serializer_class = OCRTransactionSerializer
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary="Get OCR scan status",
        description=(
            "Returns the current status of an OCR transaction. "
            "Status values: PENDING → PROCESSING → COMPLETED | FAILED. "
            "On COMPLETED, the `processed_reward` field contains the auto-created Reward object."
        )
    )
    def get_object(self):
        try:
            return OCRTransaction.objects.get(
                id=self.kwargs['pk'],
                user=self.request.user
            )
        except OCRTransaction.DoesNotExist:
            from rest_framework.exceptions import NotFound
            raise NotFound("OCR transaction not found.")
