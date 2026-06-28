import re
import os
import calendar
import threading
import logging
from decimal import Decimal
from datetime import datetime
from django.utils import timezone
from django.conf import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Thread-safe lazy EasyOCR singleton
# Each Celery worker process initialises its own reader once and caches it.
# The double-checked locking pattern prevents redundant initialisation when
# multiple threads hit the first request simultaneously.
# ---------------------------------------------------------------------------
_easyocr_reader = None
_reader_lock = threading.Lock()


def get_ocr_reader():
    global _easyocr_reader
    if _easyocr_reader is None:
        with _reader_lock:
            if _easyocr_reader is None:          # re-check inside the lock
                try:
                    import easyocr
                    use_gpu = getattr(settings, 'OCR_USE_GPU', False)
                    logger.info(f"[OCR] Initialising EasyOCR Reader (gpu={use_gpu})…")
                    _easyocr_reader = easyocr.Reader(['en'], gpu=use_gpu)
                    logger.info("[OCR] EasyOCR Reader loaded successfully.")
                except ImportError:
                    logger.error("[OCR] easyocr not installed. Run: pip install easyocr")
                except Exception as exc:
                    logger.error(f"[OCR] Failed to initialise EasyOCR: {exc}")
    return _easyocr_reader


class OCRService:
    """
    Local OCR service that:
      - Preprocesses the uploaded image (grayscale + contrast boost) via PIL
      - Runs EasyOCR on the preprocessed image
      - Parses merchant, coupon code, monetary value, expiry date and reward type
        from the extracted text using regex heuristics
    Falls back to deterministic mock output when EasyOCR is unavailable
    (useful for local development / unit tests).
    """

    # Minimum EasyOCR confidence to accept a text segment
    _CONFIDENCE_THRESHOLD = 0.30

    # ---------------------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------------------

    def process_image(self, image_path: str) -> tuple[str, list]:
        """
        Run text recognition on *image_path*.

        Returns
        -------
        raw_text : str
            Newline-joined text segments above the confidence threshold.
        raw_results : list
            Full EasyOCR payload (bbox, text, confidence) for each segment.
        """
        reader = get_ocr_reader()
        if not reader:
            logger.warning("[OCR] Reader unavailable – using mock fallback.")
            return self._get_mock_fallback_text(image_path)

        preprocessed_path = self._preprocess_image(image_path)
        try:
            results = reader.readtext(preprocessed_path, detail=1, paragraph=False)
            text_lines = [
                res[1] for res in results
                if res[2] >= self._CONFIDENCE_THRESHOLD
            ]
            raw_text = "\n".join(text_lines)
            logger.info(f"[OCR] Extracted {len(text_lines)} line(s) from image.")
            return raw_text, results
        except Exception as exc:
            logger.error(f"[OCR] EasyOCR extraction failure: {exc}")
            return self._get_mock_fallback_text(image_path)
        finally:
            # Remove temp preprocessed file (if different from the original)
            if preprocessed_path != image_path and os.path.exists(preprocessed_path):
                try:
                    os.remove(preprocessed_path)
                except OSError:
                    pass

    def parse_reward_data(self, raw_text: str) -> dict:
        """
        Parse merchant, code, value, expiry date and reward type from *raw_text*.

        Returns a dict with keys:
            merchant_name, code, value, expiry_date, reward_type, raw_text
        """
        lines = [line.strip() for line in raw_text.split('\n') if line.strip()]

        merchant_name = self._extract_merchant(lines)
        code          = self._extract_code(lines)
        value         = self._extract_value(lines)
        expiry_date   = self._extract_expiry(lines)
        reward_type   = self._infer_reward_type(lines, code)

        return {
            'merchant_name': merchant_name,
            'code':          code,
            'value':         value,
            'expiry_date':   expiry_date,
            'reward_type':   reward_type,
            'raw_text':      raw_text,
        }

    # ---------------------------------------------------------------------------
    # Image pre-processing
    # ---------------------------------------------------------------------------

    def _preprocess_image(self, image_path: str) -> str:
        """
        Convert to grayscale and boost contrast/sharpness with PIL to improve
        EasyOCR accuracy on low-quality receipt photos.

        Returns the path to the processed image; falls back to the original
        path if PIL operations fail.
        """
        try:
            from PIL import Image, ImageFilter, ImageEnhance
            img = Image.open(image_path).convert('L')          # Grayscale
            img = ImageEnhance.Contrast(img).enhance(2.0)      # Boost contrast
            img = img.filter(ImageFilter.SHARPEN)

            base, ext = os.path.splitext(image_path)
            output_path = f"{base}_ocr_pre{ext}"
            img.save(output_path)
            return output_path
        except Exception as exc:
            logger.warning(f"[OCR] Preprocessing skipped, using original: {exc}")
            return image_path

    # ---------------------------------------------------------------------------
    # Mock fallback
    # ---------------------------------------------------------------------------

    def _get_mock_fallback_text(self, image_path: str) -> tuple[str, list]:
        """Return deterministic mock text based on the image filename."""
        filename = os.path.basename(image_path).lower()
        if 'amazon' in filename:
            text = (
                "AMAZON GIFT CARD\nValue: $50.00\n"
                "Code: AMZN-FREE-VOUCH-99\nEXP: 12/31/2026\nPin: 1234"
            )
        elif 'starbucks' in filename:
            text = (
                "STARBUCKS REWARDS\nTotal: 15.75 USD\n"
                "Code: SBUX-9876-1234\nExpiry Date: 2026-12-15"
            )
        else:
            text = (
                "GENERIC MERCHANT\nCoupon value $10.00\n"
                "Code: GENERIC9988\nExpires on 2026-11-30"
            )
        return text, []

    # ---------------------------------------------------------------------------
    # Field extraction helpers
    # ---------------------------------------------------------------------------

    def _infer_reward_type(self, lines: list[str], code: str | None) -> str:
        """
        Infer the Reward.RewardType from text signals.

        Priority order:
          GIFT_CARD → LOYALTY_POINTS → CASHBACK → PAYMENT_APP_REWARD → COUPON
        """
        full_text = " ".join(lines).lower()

        if any(kw in full_text for kw in ('gift card', 'gift-card', 'giftcard')):
            return 'GIFT_CARD'
        if any(kw in full_text for kw in ('loyalty', 'points', 'pts', 'miles', 'airmiles')):
            return 'LOYALTY_POINTS'
        if any(kw in full_text for kw in ('cashback', 'cash back', 'refund', 'rebate')):
            return 'CASHBACK'
        if any(kw in full_text for kw in ('paytm', 'gpay', 'google pay', 'phonepe', 'upi reward')):
            return 'PAYMENT_APP_REWARD'
        # A redeemable code with no other signal → treat as coupon
        if code:
            return 'COUPON'
        return 'CASHBACK'

    def _extract_merchant(self, lines: list[str]) -> str:
        """
        Identify the issuer/merchant name.

        Strategy:
          1. Look for a known brand in the first 5 lines (sorted longest-first
             so multi-word brands like "Uber Eats" match before "Uber").
          2. Fall back to the first non-empty line after stripping symbols.
        """
        known_issuers = [
            'uber eats', 'google pay', 'amazon', 'walmart', 'starbucks',
            'target', 'uber', 'google', 'apple', 'netflix', 'spotify',
            'delta', 'flipkart', 'swiggy', 'zomato', 'myntra', 'ajio', 'paytm',
        ]
        # Sort descending by length so longer phrases match first
        known_issuers_sorted = sorted(known_issuers, key=len, reverse=True)

        for line in lines[:5]:
            for brand in known_issuers_sorted:
                if brand in line.lower():
                    return brand.title()

        if lines:
            clean = re.sub(r'[^\w\s-]', '', lines[0]).strip()
            if len(clean) > 3:
                return clean[:50]
        return "Unknown Issuer"

    def _extract_code(self, lines: list[str]) -> str | None:
        """
        Extract a voucher / coupon / gift-card code.

        Patterns (in priority order):
          XXXX-XXXX-XXXX-XXXX  →  XXXX-XXXX-XXXX  →  12-16 alphanum  →  8-11 alphanum
        Lines that explicitly mention 'code', 'voucher', etc. are checked first.
        Lines containing metadata keywords (total, value, …) are skipped.
        """
        patterns = [
            r'\b[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}\b',
            r'\b[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}\b',
            r'\b[A-Z0-9]{12,16}\b',
            r'\b[A-Z0-9]{8,11}\b',
        ]
        code_keywords    = ('code', 'voucher', 'coupon', 'promo', 'pin', 'serial', 'redeem')
        exclude_keywords = ('total', 'value', 'amount', 'expiry', 'date', 'valid', 'phone', 'expires')

        def _first_match(line: str) -> str | None:
            for pattern in patterns:
                for match in re.findall(pattern, line, re.IGNORECASE):
                    if not match.replace('-', '').isdigit():
                        return match.upper()
            return None

        # Pass 1 – lines that contain code-specific keywords
        for line in lines:
            if any(kw in line.lower() for kw in code_keywords):
                result = _first_match(line)
                if result:
                    return result

        # Pass 2 – all other lines, skipping metadata lines
        for line in lines:
            if any(kw in line.lower() for kw in exclude_keywords):
                continue
            result = _first_match(line)
            if result:
                return result

        return None

    def _extract_value(self, lines: list[str]) -> Decimal | None:
        """
        Extract a monetary / point value.

        Handles:  $10.00 · 10.00 USD · 500 pts · ₹250
        """
        money_pattern = re.compile(
            r'[\$₹€£]?\s*\d+(?:\.\d{1,2})?\s*(?:usd|inr|eur|gbp|pts|points)?' 
            r'|\b\d+(?:\.\d{1,2})?\s*(?:usd|inr|eur|gbp|pts|points)\b',
            re.IGNORECASE,
        )
        value_keywords = ('total', 'value', 'amount', 'balance', 'price', 'worth', 'reward')

        # Prefer lines that explicitly mention a value keyword
        for line in lines:
            if any(kw in line.lower() for kw in value_keywords):
                match = money_pattern.search(line)
                if match:
                    val = self._clean_decimal(match.group(0))
                    if val:
                        return val

        # Fallback: first monetary match anywhere
        for line in lines:
            match = money_pattern.search(line)
            if match:
                val = self._clean_decimal(match.group(0))
                if val:
                    return val
        return None

    def _clean_decimal(self, text: str) -> Decimal | None:
        try:
            cleaned = re.sub(r'[^\d.]', '', text)
            if cleaned and cleaned != '.':
                return Decimal(cleaned)
        except Exception:
            pass
        return None

    def _extract_expiry(self, lines: list[str]) -> datetime | None:
        """
        Extract the expiry / valid-through date.

        Supported formats:
          MM/DD/YYYY · YYYY-MM-DD · DD-MM-YYYY · MM/YYYY · Month DD, YYYY
        Lines containing expiry keywords are prioritised; any future date in
        the remaining lines is used as a last resort.
        """
        date_patterns = [
            r'\b\d{2}/\d{2}/\d{4}\b',                      # MM/DD/YYYY
            r'\b\d{4}-\d{2}-\d{2}\b',                      # YYYY-MM-DD
            r'\b\d{2}-\d{2}-\d{4}\b',                      # DD-MM-YYYY
            r'\b\d{1,2}/\d{4}\b',                          # MM/YYYY
            r'\b[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4}\b',     # Month DD[,] YYYY
        ]
        expiry_keywords = ('exp', 'expiry', 'expiration', 'valid', 'thru', 'expires', 'till', 'end', 'use by')

        def _search_line(line: str) -> datetime | None:
            for pattern in date_patterns:
                match = re.search(pattern, line, re.IGNORECASE)
                if match:
                    parsed = self._parse_date_string(match.group(0))
                    if parsed:
                        return parsed
            return None

        # Pass 1 – lines with expiry signals
        for line in lines:
            if any(kw in line.lower() for kw in expiry_keywords):
                result = _search_line(line)
                if result:
                    return result

        # Pass 2 – any future date in remaining lines
        for line in lines:
            result = _search_line(line)
            if result and result > timezone.now():
                return result
        return None

    def _parse_date_string(self, date_str: str) -> datetime | None:
        formats = [
            '%m/%d/%Y', '%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y',
            '%b %d, %Y', '%B %d, %Y', '%b %d %Y', '%B %d %Y',
            '%m/%Y',
        ]
        for fmt in formats:
            try:
                parsed = datetime.strptime(date_str, fmt)
                if fmt == '%m/%Y':
                    # Set to the last day of that month
                    last_day = calendar.monthrange(parsed.year, parsed.month)[1]
                    parsed = parsed.replace(day=last_day)
                return timezone.make_aware(parsed)
            except ValueError:
                continue
        return None
