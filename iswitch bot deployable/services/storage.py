import os
import uuid
import mimetypes
import logging
from pathlib import Path
from config import RECEIPTS_DIR, MEDIA_DIR, ALLOWED_RECEIPT_EXTENSIONS, MAX_RECEIPT_SIZE_MB

logger = logging.getLogger("iswitch.storage")

class StorageService:
    def __init__(self, receipts_dir: Path = RECEIPTS_DIR, media_dir: Path = MEDIA_DIR):
        self.receipts_dir = receipts_dir
        self.media_dir = media_dir
        self.receipts_dir.mkdir(parents=True, exist_ok=True)
        self.media_dir.mkdir(parents=True, exist_ok=True)

    def validate_receipt_file(self, filename: str, file_size: int) -> tuple[bool, str]:
        ext = Path(filename).suffix.lower()
        if ext not in ALLOWED_RECEIPT_EXTENSIONS:
            return False, f"Unsupported file type '{ext}'. Allowed: JPG, PNG, PDF."
        
        max_bytes = MAX_RECEIPT_SIZE_MB * 1024 * 1024
        if file_size > max_bytes:
            return False, f"File size exceeds maximum allowed {MAX_RECEIPT_SIZE_MB}MB."

        return True, ""

    async def save_receipt(self, file_bytes: bytes, original_filename: str, order_id: int, customer_id: int) -> dict:
        ext = Path(original_filename).suffix.lower()
        if not ext or ext not in ALLOWED_RECEIPT_EXTENSIONS:
            ext = ".jpg"

        # Security: Enforce maximum receipt file size limit (10MB)
        if len(file_bytes) > MAX_RECEIPT_SIZE_MB * 1024 * 1024:
            raise ValueError(f"Receipt exceeds maximum allowed size ({MAX_RECEIPT_SIZE_MB}MB).")
        
        unique_name = f"receipt_ord{order_id}_c{customer_id}_{uuid.uuid4().hex[:12]}{ext}"
        destination = self.receipts_dir / unique_name
        
        with open(destination, "wb") as f:
            f.write(file_bytes)

        file_size = len(file_bytes)
        mime_type, _ = mimetypes.guess_type(str(destination))
        if not mime_type:
            mime_type = "image/jpeg" if ext in [".jpg", ".jpeg"] else ("application/pdf" if ext == ".pdf" else "image/png")

        logger.info(f"Saved receipt to {destination} (size: {file_size} bytes)")
        return {
            "file_path": str(destination),
            "file_name": unique_name,
            "file_type": mime_type,
            "file_size": file_size
        }

    async def save_product_media(self, file_bytes: bytes, original_filename: str, product_id: int = None) -> str:
        ext = Path(original_filename).suffix.lower()
        if not ext or ext not in {".jpg", ".jpeg", ".png", ".webp"}:
            ext = ".jpg"

        # Security: Enforce 10MB maximum upload limit for media
        if len(file_bytes) > 10 * 1024 * 1024:
            raise ValueError("Media file exceeds maximum allowed size (10MB).")
        
        prefix = f"prod_{product_id}_" if product_id else "media_"
        unique_name = f"{prefix}{uuid.uuid4().hex[:12]}{ext}"
        destination = self.media_dir / unique_name

        with open(destination, "wb") as f:
            f.write(file_bytes)

        logger.info(f"Saved product media to {destination}")
        return str(destination)

# Global storage service
storage_service = StorageService()
