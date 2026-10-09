from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse

from mekiki_engine.deps import DataDirDep, SessionDep, SettingsDep, UserDep
from mekiki_engine.schemas import ItemOut, ItemPhotoOut, ItemUpdate, PhotoUpload, SaleUpsert
from mekiki_engine.services import photos, portfolio

router = APIRouter(prefix="/items", tags=["items"])


@router.get("/{item_id}")
def read_item(item_id: int, session: SessionDep, user: UserDep, settings: SettingsDep) -> ItemOut:
    return portfolio.item_detail(session, user.id, settings, item_id)


@router.patch("/{item_id}")
def update_item(
    item_id: int, payload: ItemUpdate, session: SessionDep, user: UserDep, settings: SettingsDep
) -> ItemOut:
    return portfolio.update_item(session, user.id, settings, item_id, payload)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_item(item_id: int, session: SessionDep, user: UserDep, data_dir: DataDirDep) -> None:
    """Refused while the card is sold: its sale would leave the books with it."""
    try:
        portfolio.delete_item(session, user.id, item_id)
    except portfolio.SoldError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(error)) from error
    photos.remove_item_files(data_dir, [item_id])


@router.post("/{item_id}/photos", status_code=status.HTTP_201_CREATED)
def add_photo(
    item_id: int, payload: PhotoUpload, session: SessionDep, user: UserDep, data_dir: DataDirDep
) -> list[ItemPhotoOut]:
    try:
        return photos.add_photo(session, data_dir, user.id, item_id, payload.content_base64)
    except photos.PhotoError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)) from error


@router.get("/{item_id}/photos/{photo_id}")
def read_photo(
    item_id: int, photo_id: int, session: SessionDep, user: UserDep, data_dir: DataDirDep
) -> FileResponse:
    path, content_type = photos.photo_file(session, data_dir, user.id, item_id, photo_id)
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="fichier de la photo introuvable")
    return FileResponse(path, media_type=content_type)


@router.post("/{item_id}/photos/{photo_id}/first")
def move_photo_first(
    item_id: int, photo_id: int, session: SessionDep, user: UserDep
) -> list[ItemPhotoOut]:
    return photos.move_to_front(session, user.id, item_id, photo_id)


@router.delete("/{item_id}/photos/{photo_id}")
def delete_photo(
    item_id: int, photo_id: int, session: SessionDep, user: UserDep, data_dir: DataDirDep
) -> list[ItemPhotoOut]:
    return photos.delete_photo(session, data_dir, user.id, item_id, photo_id)


@router.put("/{item_id}/sale")
def record_sale(
    item_id: int, payload: SaleUpsert, session: SessionDep, user: UserDep, settings: SettingsDep
) -> ItemOut:
    return portfolio.record_sale(session, user.id, settings, item_id, payload)


@router.delete("/{item_id}/sale")
def cancel_sale(item_id: int, session: SessionDep, user: UserDep, settings: SettingsDep) -> ItemOut:
    return portfolio.cancel_sale(session, user.id, settings, item_id)
