"""Media metadata and file extension normalization helpers."""

import os
from pathlib import PurePath


def normalize_extension(filename: str | None, mime_type: str | None = None) -> str:
    """Return lowercase dot-prefixed file extension (e.g. '.pdf', '.mp4') or empty string."""
    if filename:
        suffix = PurePath(filename).suffix.lower()
        if suffix:
            return suffix
    if mime_type:
        mapping = {
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/webp": ".webp",
            "image/gif": ".gif",
            "video/mp4": ".mp4",
            "video/quicktime": ".mov",
            "video/x-matroska": ".mkv",
            "audio/mpeg": ".mp3",
            "audio/ogg": ".ogg",
            "audio/mp4": ".m4a",
            "application/pdf": ".pdf",
            "application/zip": ".zip",
        }
        return mapping.get(mime_type.lower(), "")
    return ""


def safe_filename(name: str | None, fallback: str = "media.bin") -> str:
    """Prevent path traversal in cached media filenames."""
    if not name:
        return fallback
    base = os.path.basename(name).strip()
    cleaned = "".join(ch if ch.isalnum() or ch in ("-", "_", ".") else "_" for ch in base)
    return cleaned[:120] or fallback
