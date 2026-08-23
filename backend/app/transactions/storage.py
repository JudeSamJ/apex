import os
import uuid
import logging

logger = logging.getLogger(__name__)

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/heic", "image/webp", "application/pdf"}
MAX_RECEIPT_BYTES = 10 * 1024 * 1024  # 10MB

# Local disk under backend/uploads/receipts/ — fine for local dev and a
# single-instance deployment. Swapping this module for an S3-backed
# implementation later is a drop-in change (same save/read/delete
# signature), same pattern as the pluggable secrets/email providers.
_UPLOAD_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "uploads", "receipts")


def _safe_filename(filename: str) -> str:
    # Strip any path components a malicious client-supplied filename might
    # carry (e.g. "../../etc/passwd") — only the basename is ever trusted.
    return os.path.basename(filename or "receipt")


def save_receipt(transaction_id: str, filename: str, data: bytes) -> str:
    """Persist receipt bytes to disk and return the storage path (relative
    to the upload root, safe to store in the DB)."""
    txn_dir = os.path.join(_UPLOAD_ROOT, transaction_id)
    os.makedirs(txn_dir, exist_ok=True)

    unique_name = f"{uuid.uuid4()}_{_safe_filename(filename)}"
    full_path = os.path.join(txn_dir, unique_name)
    with open(full_path, "wb") as f:
        f.write(data)

    return os.path.join(transaction_id, unique_name)


def read_receipt(storage_path: str) -> bytes:
    full_path = os.path.join(_UPLOAD_ROOT, storage_path)
    # Guard against a stored path ever escaping the upload root.
    if not os.path.abspath(full_path).startswith(os.path.abspath(_UPLOAD_ROOT)):
        raise ValueError("Invalid storage path")
    with open(full_path, "rb") as f:
        return f.read()


def delete_receipt(storage_path: str) -> None:
    full_path = os.path.join(_UPLOAD_ROOT, storage_path)
    if not os.path.abspath(full_path).startswith(os.path.abspath(_UPLOAD_ROOT)):
        raise ValueError("Invalid storage path")
    try:
        os.remove(full_path)
    except FileNotFoundError:
        pass
