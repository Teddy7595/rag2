from __future__ import annotations

from pathlib import Path
import re

from fastapi import APIRouter, Request
from fastapi import File, HTTPException, Query, UploadFile

from app.core.app_context import get_app_context_from_request
from app.storage.service import UploadStorage
from app.knowledge.events import DocumentIngestRequest, REQUEST_KNOWLEDGE_DOCUMENT_INGEST

router = APIRouter(tags=["storage"])


def _sanitize_engram_id(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "-", (value or "").strip()).strip("-._")
    return cleaned or ""


def _get_storage(request: Request) -> UploadStorage:
    context = get_app_context_from_request(request)
    storage = context.services.get("storage")
    if not isinstance(storage, UploadStorage):
        raise RuntimeError("Storage service not available")
    return storage


def _build_document_ingest_request(
    resolved_path: Path,
    *,
    relative_path: str,
    engram_id: str | None,
    title: str | None,
    chunk_size: int,
    chunk_overlap: int,
) -> tuple[DocumentIngestRequest, str]:
    suffix = resolved_path.suffix.lower()
    tags: list[str] = ["vault", "chat_ingest"]
    safe_engram = _sanitize_engram_id(str(engram_id or "")) if engram_id else ""
    if safe_engram:
        tags.append(f"engram:{safe_engram}")

    if suffix == ".pdf":
        payload = DocumentIngestRequest(
            title=title or resolved_path.stem,
            pdf_path=str(resolved_path),
            source_uri=f"vault://{relative_path}",
            tags=tuple(tags + ["pdf"]),
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
    else:
        text = resolved_path.read_text(encoding="utf-8", errors="ignore")
        payload = DocumentIngestRequest(
            title=title or resolved_path.stem,
            raw_text=text,
            source_uri=f"vault://{relative_path}",
            tags=tuple(tags + ["text"]),
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
    return payload, safe_engram


@router.get("/api/storage/overview")
async def storage_overview(request: Request) -> dict[str, object]:
    return _get_storage(request).overview()


@router.get("/api/storage/public")
async def list_public_files(request: Request) -> list[str]:
    return list(_get_storage(request).list_public_files())


@router.get("/api/storage/uploads")
async def list_upload_files(request: Request) -> list[str]:
    return list(_get_storage(request).list_upload_files())


@router.get("/api/storage/vault/files")
async def list_vault_files(request: Request, limit: int = Query(default=200, ge=1, le=2000)) -> list[dict[str, object]]:
    return _get_storage(request).list_vault_files(limit=limit)


@router.get("/api/storage/chats/{session_id}/assets")
async def list_chat_assets(request: Request, session_id: str) -> list[str]:
    return list(_get_storage(request).list_chat_assets(session_id))


@router.post("/api/storage/chats/{session_id}/assets")
async def upload_chat_asset(request: Request, session_id: str, file: UploadFile = File(...)) -> dict[str, object]:
    storage = _get_storage(request)
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    return storage.save_chat_asset(session_id, original_name=file.filename or "asset.bin", payload=content)


@router.get("/api/storage/engrams/{engram_id}/content")
async def list_engram_content_assets(request: Request, engram_id: str) -> list[str]:
    return list(_get_storage(request).list_engram_content_assets(engram_id))


@router.post("/api/storage/engrams/{engram_id}/content")
async def upload_engram_content_asset(request: Request, engram_id: str, file: UploadFile = File(...)) -> dict[str, object]:
    storage = _get_storage(request)
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    return storage.save_engram_content_asset(engram_id, original_name=file.filename or "asset.bin", payload=content)


@router.post("/api/storage/engrams/{engram_id}/content/digest")
async def upload_and_digest_engram_content_assets(
    request: Request,
    engram_id: str,
    files: list[UploadFile] = File(...),
    chunk_size: int = Query(default=180, ge=32, le=1200),
    chunk_overlap: int = Query(default=40, ge=0, le=300),
) -> dict[str, object]:
    context = get_app_context_from_request(request)
    storage = _get_storage(request)
    safe_engram = _sanitize_engram_id(engram_id)
    if not safe_engram:
        raise HTTPException(status_code=400, detail="Invalid engram id")
    if not files:
        raise HTTPException(status_code=400, detail="At least one file is required")

    processed: list[dict[str, object]] = []
    for upload in files:
        content = await upload.read()
        if not content:
            continue
        saved = storage.save_engram_content_asset(safe_engram, original_name=upload.filename or "asset.bin", payload=content)
        relative_path = str(saved.get("relative_path") or "")
        resolved = storage.resolve_vault_path(relative_path)
        if not resolved:
            continue

        ingest_request, _ = _build_document_ingest_request(
            resolved,
            relative_path=relative_path,
            engram_id=safe_engram,
            title=None,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        ingested = context.event_bus.request(
            REQUEST_KNOWLEDGE_DOCUMENT_INGEST,
            ingest_request,
            source_module="storage.routes",
        )
        processed.append(
            {
                "upload": saved,
                "digest": ingested,
            }
        )

    if not processed:
        raise HTTPException(status_code=400, detail="No valid non-empty files were uploaded")

    return {
        "engram_id": safe_engram,
        "processed_count": len(processed),
        "items": processed,
        "last_relative_path": str((processed[-1].get("upload") or {}).get("relative_path") or ""),
    }


@router.post("/api/storage/engrams/avatar")
async def upload_engram_avatar(request: Request, file: UploadFile = File(...)) -> dict[str, object]:
    storage = _get_storage(request)
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    return storage.save_engram_avatar(original_name=file.filename or "avatar.png", payload=content)


@router.post("/api/storage/vault/ingest")
async def ingest_vault_file(
    request: Request,
    relative_path: str = Query(..., min_length=1),
    engram_id: str | None = Query(default=None),
    title: str | None = Query(default=None),
    chunk_size: int = Query(default=180, ge=32, le=1200),
    chunk_overlap: int = Query(default=40, ge=0, le=300),
) -> dict[str, object]:
    context = get_app_context_from_request(request)
    storage = _get_storage(request)
    resolved = storage.resolve_vault_path(relative_path)
    if not resolved:
        raise HTTPException(status_code=404, detail="Vault file not found")

    payload, safe_engram = _build_document_ingest_request(
        resolved,
        relative_path=relative_path,
        engram_id=engram_id,
        title=title,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )

    ingested = context.event_bus.request(
        REQUEST_KNOWLEDGE_DOCUMENT_INGEST,
        payload,
        source_module="storage.routes",
    )
    return {
        "relative_path": Path(relative_path).as_posix(),
        "engram_id": safe_engram or None,
        "ingested": ingested,
    }
