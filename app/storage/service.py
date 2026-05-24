from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

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

    @staticmethod
    def _sanitize_segment(value: str) -> str:
        cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "-", (value or "").strip()).strip("-._")
        return cleaned or "default"

    @staticmethod
    def _clean_filename(file_name: str) -> str:
        candidate = Path(file_name or "asset.bin").name
        return candidate or "asset.bin"

    def _resolve_unique_path(self, target_dir: Path, original_name: str) -> Path:
        base_name = self._clean_filename(original_name)
        stem = Path(base_name).stem
        suffix = Path(base_name).suffix
        candidate = target_dir / base_name
        index = 1
        while candidate.exists():
            candidate = target_dir / f"{stem}_{index}{suffix}"
            index += 1
        return candidate

    def chat_assets_dir(self, session_id: str) -> Path:
        safe_session = self._sanitize_segment(session_id)
        directory = self.uploads_dir / "chats" / safe_session
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def list_chat_assets(self, session_id: str) -> tuple[str, ...]:
        directory = self.chat_assets_dir(session_id)
        return tuple(sorted(item.name for item in directory.iterdir() if item.is_file()))

    def engram_content_dir(self, engram_id: str) -> Path:
        safe_engram = self._sanitize_segment(engram_id)
        directory = self.uploads_dir / "engrams" / safe_engram / "content"
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def list_engram_content_assets(self, engram_id: str) -> tuple[str, ...]:
        directory = self.engram_content_dir(engram_id)
        return tuple(sorted(item.name for item in directory.iterdir() if item.is_file()))

    def save_chat_asset(self, session_id: str, *, original_name: str, payload: bytes) -> dict[str, object]:
        directory = self.chat_assets_dir(session_id)
        target = self._resolve_unique_path(directory, original_name)
        target.write_bytes(payload)
        relative = target.relative_to(self.vault_dir).as_posix()
        return {
            "session_id": self._sanitize_segment(session_id),
            "file_name": target.name,
            "relative_path": relative,
            "public_url": f"/uploads/{target.relative_to(self.uploads_dir).as_posix()}",
            "size_bytes": target.stat().st_size,
        }

    def save_engram_content_asset(self, engram_id: str, *, original_name: str, payload: bytes) -> dict[str, object]:
        safe_engram = self._sanitize_segment(engram_id)
        directory = self.engram_content_dir(safe_engram)
        target = self._resolve_unique_path(directory, original_name)
        target.write_bytes(payload)
        relative = target.relative_to(self.vault_dir).as_posix()
        return {
            "engram_id": safe_engram,
            "file_name": target.name,
            "relative_path": relative,
            "public_url": f"/uploads/{target.relative_to(self.uploads_dir).as_posix()}",
            "size_bytes": target.stat().st_size,
        }

    def save_engram_avatar(self, *, original_name: str, payload: bytes) -> dict[str, object]:
        directory = self.uploads_dir / "engrams"
        directory.mkdir(parents=True, exist_ok=True)
        target = self._resolve_unique_path(directory, original_name)
        target.write_bytes(payload)
        return {
            "file_name": target.name,
            "relative_path": target.relative_to(self.vault_dir).as_posix(),
            "public_url": f"/uploads/{target.relative_to(self.uploads_dir).as_posix()}",
            "size_bytes": target.stat().st_size,
        }

    def list_vault_files(self, *, limit: int = 500) -> list[dict[str, object]]:
        if limit <= 0:
            return []
        rows: list[dict[str, object]] = []
        for path in sorted(self.vault_dir.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(self.vault_dir).as_posix()
            rows.append(
                {
                    "name": path.name,
                    "relative_path": relative,
                    "size_bytes": path.stat().st_size,
                }
            )
            if len(rows) >= limit:
                break
        return rows

    def resolve_vault_path(self, relative_path: str) -> Path | None:
        safe_relative = Path(relative_path.strip())
        if safe_relative.is_absolute():
            return None
        resolved = (self.vault_dir / safe_relative).resolve()
        try:
            resolved.relative_to(self.vault_dir.resolve())
        except ValueError:
            return None
        if not resolved.exists() or not resolved.is_file():
            return None
        return resolved