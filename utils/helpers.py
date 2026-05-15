import io
import re
import uuid
from pathlib import Path

from fastapi import UploadFile
from PIL import Image

from core.config import UPLOAD_DIR


def slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_-]+', '-', text)
    return text.strip('-')


def fmt_money(value) -> str:
    if value is None:
        return "—"
    if value >= 1_000_000:
        return f"₽ {value / 1_000_000:.1f} млн"
    if value >= 1_000:
        return f"₽ {value / 1_000:.0f} тыс"
    return f"₽ {value:.0f}"


async def save_image(file: UploadFile, folder: str, size: tuple) -> str:
    ext = Path(file.filename).suffix.lower() or ".jpg"
    filename = f"{uuid.uuid4().hex}{ext}"
    dest = UPLOAD_DIR / folder / filename
    dest.parent.mkdir(parents=True, exist_ok=True)
    contents = await file.read()
    img = Image.open(io.BytesIO(contents)).convert("RGB")
    img.thumbnail(size, Image.LANCZOS)
    img.save(dest, quality=85, optimize=True)
    return f"/static/uploads/{folder}/{filename}"
