from django.urls import path
from ocr.views import OCRScanView, OCRScanListView, OCRScanDetailView

app_name = 'ocr'

urlpatterns = [
    # Upload a new image for OCR processing
    path('scan/', OCRScanView.as_view(), name='ocr_scan'),
    # List all transaction scans
    path('scans/', OCRScanListView.as_view(), name='ocr_scan_list'),
    # Poll status of a specific scan
    path('scans/<uuid:pk>/', OCRScanDetailView.as_view(), name='ocr_scan_detail'),
]
