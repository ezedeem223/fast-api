"""File and media utility helpers."""

from __future__ import annotations

import base64
from io import BytesIO
from pathlib import Path
from typing import Optional

import aiofiles
import qrcode
from fastapi import UploadFile

from .common import logger

UPLOAD_ROOT = Path("uploads")


def generate_qr_code(data: str) -> str:
    """Generate a QR code for the given data and return it as base64 PNG string."""
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffered = BytesIO()
    img.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode()


async def save_upload_file(upload_file: UploadFile, *, folder: Optional[Path] = None) -> str:
    """Persist an uploaded file asynchronously and return its storage path."""
    target_dir = (folder or UPLOAD_ROOT)
    target_dir.mkdir(parents=True, exist_ok=True)
    file_location = target_dir / upload_file.filename
    async with aiofiles.open(file_location, "wb") as out_file:
        content = await upload_file.read()
        await out_file.write(content)
    logger.debug("Stored upload at %s", file_location)
    return str(file_location)


__all__ = ["generate_qr_code", "save_upload_file", "UPLOAD_ROOT"]
