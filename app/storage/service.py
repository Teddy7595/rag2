from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.core.settings import AppSettings


@dataclass(frozen=True)
class StorageOverview:
    vault_dir: str
    public_dir: str
    uploads_dir: str
    public_mount: str
    uploads_mount: str
    public_files: tuple[str, ...]
    upload_files: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "vault_dir": self.vault_dir,
            "public_dir": self.public_dir,
            "uploads_dir": self.uploads_dir,
            "public_mount": self.public_mount,
            "uploads_mount": self.uploads_mount,
            "public_files": list(self.public_files),
            "upload_files": list(self.upload_files),
            "public_file_count": len(self.public_files),
            "upload_file_count": len(self.upload_files),
        }


class UploadStorage:
    def __init__(self, settings: AppSettings) -> None:
        self.vault_dir = settings.vault_dir
        self.public_dir = self.vault_dir / "public"
        self.uploads_dir = self.vault_dir / "uploads"
        self.ensure_directories()

    def ensure_directories(self) -> None:
        self.public_dir.mkdir(parents=True, exist_ok=True)
        self.uploads_dir.mkdir(parents=True, exist_ok=True)

    def _list_files(self, directory: Path) -> tuple[str, ...]:
        if not directory.exists():
            return ()
        return tuple(sorted(item.name for item in directory.iterdir() if item.is_file()))

    def list_public_files(self) -> tuple[str, ...]:
        return self._list_files(self.public_dir)

    def list_upload_files(self) -> tuple[str, ...]:
        return self._list_files(self.uploads_dir)

    def overview(self) -> dict[str, object]:
        public_files = self.list_public_files()
        upload_files = self.list_upload_files()
        return StorageOverview(
            vault_dir=str(self.vault_dir),
            public_dir=str(self.public_dir),
            uploads_dir=str(self.uploads_dir),
            public_mount="/public",
            uploads_mount="/uploads",
            public_files=public_files,
            upload_files=upload_files,
        ).as_dict()