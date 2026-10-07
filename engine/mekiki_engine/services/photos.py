"""Photos of cards in stock, stored as files in the data folder (photos/<item id>/)."""

from __future__ import annotations

import base64
import binascii
import shutil
import uuid
from collections.abc import Iterable
from pathlib import Path

from sqlalchemy.orm import Session

from mekiki_engine.models import ItemPhoto
from mekiki_engine.schemas import ItemPhotoOut
from mekiki_engine.services.portfolio import NotFoundError, get_item

# eBay takes up to 24 photos and Vinted 20; a dozen covers front, back and close-ups.
MAX_PHOTOS = 12
MAX_BYTES = 8 * 1024 * 1024
EXTENSIONS = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}


class PhotoError(ValueError):
    """The upload is not an image the marketplaces accept, or one too many."""


def photos_dir(data_dir: Path, item_id: int) -> Path:
    return data_dir / "photos" / str(item_id)


def image_type(content: bytes) -> str | None:
    """The image's type from its first bytes: the file name or a declared type can lie."""
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp"
    return None


def list_photos(session: Session, user_id: int, item_id: int) -> list[ItemPhotoOut]:
    item = get_item(session, user_id, item_id)
    return [ItemPhotoOut.model_validate(photo) for photo in item.photos]


def add_photo(
    session: Session, data_dir: Path, user_id: int, item_id: int, content_base64: str
) -> list[ItemPhotoOut]:
    item = get_item(session, user_id, item_id)
    if len(item.photos) >= MAX_PHOTOS:
        raise PhotoError(f"{MAX_PHOTOS} photos au maximum par carte")
    # Browsers send data URLs ("data:image/jpeg;base64,..."): keep what follows the comma.
    try:
        content = base64.b64decode(content_base64.rpartition(",")[2], validate=True)
    except (binascii.Error, ValueError) as error:
        raise PhotoError("image illisible") from error
    if len(content) > MAX_BYTES:
        raise PhotoError("image trop lourde (8 Mo au maximum)")
    content_type = image_type(content)
    if content_type is None:
        raise PhotoError("format non pris en charge : JPEG, PNG ou WebP")

    folder = photos_dir(data_dir, item.id)
    folder.mkdir(parents=True, exist_ok=True)
    file_name = f"{uuid.uuid4().hex}.{EXTENSIONS[content_type]}"
    (folder / file_name).write_bytes(content)
    position = max((photo.position for photo in item.photos), default=-1) + 1
    item.photos.append(ItemPhoto(file_name=file_name, content_type=content_type, position=position))
    session.commit()
    return [ItemPhotoOut.model_validate(photo) for photo in item.photos]


def photo_file(
    session: Session, data_dir: Path, user_id: int, item_id: int, photo_id: int
) -> tuple[Path, str]:
    photo = _get_photo(session, user_id, item_id, photo_id)
    return photos_dir(data_dir, item_id) / photo.file_name, photo.content_type


def item_photo_files(session: Session, data_dir: Path, user_id: int, item_id: int) -> list[Path]:
    """Files of an item's photos, in order, for a marketplace listing."""
    item = get_item(session, user_id, item_id)
    return [photos_dir(data_dir, item.id) / photo.file_name for photo in item.photos]


def delete_photo(
    session: Session, data_dir: Path, user_id: int, item_id: int, photo_id: int
) -> list[ItemPhotoOut]:
    photo = _get_photo(session, user_id, item_id, photo_id)
    item = photo.item
    (photos_dir(data_dir, item_id) / photo.file_name).unlink(missing_ok=True)
    item.photos.remove(photo)
    session.commit()
    return [ItemPhotoOut.model_validate(p) for p in item.photos]


def move_to_front(
    session: Session, user_id: int, item_id: int, photo_id: int
) -> list[ItemPhotoOut]:
    """Makes a photo the listing's main one, keeping the others in their order."""
    photo = _get_photo(session, user_id, item_id, photo_id)
    item = photo.item
    ordered = [photo, *(p for p in item.photos if p.id != photo.id)]
    for position, each in enumerate(ordered):
        each.position = position
    session.commit()
    session.refresh(item)
    return [ItemPhotoOut.model_validate(p) for p in item.photos]


def remove_item_files(data_dir: Path, item_ids: Iterable[int]) -> None:
    """Deletes the photo folders of deleted items; their rows went with the items."""
    for item_id in item_ids:
        shutil.rmtree(photos_dir(data_dir, item_id), ignore_errors=True)


def _get_photo(session: Session, user_id: int, item_id: int, photo_id: int) -> ItemPhoto:
    item = get_item(session, user_id, item_id)
    photo = next((p for p in item.photos if p.id == photo_id), None)
    if photo is None:
        raise NotFoundError(f"photo {photo_id} not found")
    return photo
