from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from mekiki_engine.deps import DataDirDep, UserDep
from mekiki_engine.schemas import BackupOut, BackupsOut
from mekiki_engine.services import backups

router = APIRouter(prefix="/backups", tags=["backups"])

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


def _restore_allowed(request: Request) -> bool:
    # Served to other machines, the engine holds other people's books: only the computer
    # the database lives on may put an old copy back.
    return request.app.state.config.host in LOOPBACK_HOSTS


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
    return BackupOut.model_validate(backups.create_backup(request.app.state.db_engine, data_dir))


@router.post("/{name}/restore")
def restore_backup(name: str, request: Request, data_dir: DataDirDep, _user: UserDep) -> BackupOut:
    """Puts the copy back; returns the copy of the database taken just before."""
    if not _restore_allowed(request):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "restauration possible seulement sur l'ordinateur qui garde la base",
        )
    try:
        before = backups.restore(request.app.state.db_engine, data_dir, name)
    except backups.BackupNotFoundError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "sauvegarde introuvable") from error
    return BackupOut.model_validate(before)
