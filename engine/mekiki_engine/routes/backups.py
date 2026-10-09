from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import func, select

from mekiki_engine import auth
from mekiki_engine.deps import DataDirDep, SessionDep, UserDep
from mekiki_engine.models import User
from mekiki_engine.schemas import BackupOut, BackupsOut, RestoreRequest
from mekiki_engine.services import backups

router = APIRouter(prefix="/backups", tags=["backups"])

def _restore_allowed(request: Request) -> bool:
    # Served to other machines, the engine holds other people's books: only the computer
    # the database lives on may put an old copy back.
    return bool(request.app.state.config.loopback)


@router.get("")
def list_backups(request: Request, data_dir: DataDirDep, _user: UserDep) -> BackupsOut:
    return BackupsOut(
        folder=str(backups.folder(data_dir)),
        backups=[BackupOut.model_validate(b) for b in backups.list_backups(data_dir)],
        restore_allowed=_restore_allowed(request),
        last_error=request.app.state.backup_error,
    )


@router.post("", status_code=status.HTTP_201_CREATED)
def create_backup(request: Request, data_dir: DataDirDep, _user: UserDep) -> BackupOut:
    copy = backups.create_backup(request.app.state.db_engine, data_dir, kind="manual")
    return BackupOut.model_validate(copy)


@router.post("/{name}/restore")
def restore_backup(
    name: str,
    payload: RestoreRequest,
    request: Request,
    session: SessionDep,
    data_dir: DataDirDep,
    user: UserDep,
) -> BackupOut:
    """Puts the copy back; returns the copy of the database taken just before.

    A restore takes every account on this computer back in time: only its first account may
    do it, and only with its password.
    """
    if not _restore_allowed(request):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "restauration possible seulement sur l'ordinateur qui garde la base",
        )
    if user.id != session.scalar(select(func.min(User.id))):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "seul le premier compte créé sur cet ordinateur peut restaurer une sauvegarde",
        )
    if not auth.verify_password(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "mot de passe incorrect")
    try:
        before = backups.restore(request.app.state.db_engine, data_dir, name)
    except backups.BackupNotFoundError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "sauvegarde introuvable") from error
    except backups.BackupUnreadableError as error:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"sauvegarde illisible ({error}) : la base actuelle n'a pas été touchée",
        ) from error
    return BackupOut.model_validate(before)
