from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha1
from math import sqrt
from pathlib import Path
import re

from pypdf import PdfReader

from app.core.base_entity import BaseEntity
from app.knowledge.application.ports import KnowledgeRepositoryPort
from app.knowledge.domain import KnowledgeEntry
from app.knowledge.events import DocumentIngestRequest, DocumentListRequest, DocumentOverviewRequest


def _tokenize(text: str) -> tuple[str, ...]:
    seen: set[str] = set()
    tokens: list[str] = []
    for token in re.findall(r"[a-z0-9áéíóúñ]+", text.lower()):
        if token in seen:
            continue
        seen.add(token)
        tokens.append(token)
    return tuple(tokens)


def _embedding_from_tokens(tokens: tuple[str, ...], dimensions: int = 64) -> list[float]:
    vector = [0.0] * dimensions
    for token in tokens:
        digest = sha1(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % dimensions
        vector[index] += 1.0

    norm = sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [round(value / norm, 6) for value in vector]


def _chunk_words(text: str, *, chunk_size: int, overlap: int) -> list[str]:
    words = text.split()
    if not words:
        return []

    safe_chunk_size = max(1, chunk_size)
    safe_overlap = max(0, min(overlap, safe_chunk_size - 1))
    chunks: list[str] = []
    start = 0
    while start < len(words):
        end = min(len(words), start + safe_chunk_size)
        chunk = " ".join(words[start:end]).strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(words):
            break
        start = end - safe_overlap
    return chunks


def _read_pdf_pages(pdf_path: str) -> list[str]:
    reader = PdfReader(pdf_path)
    pages: list[str] = []
    for page in reader.pages:
        extracted = page.extract_text() or ""
        pages.append(extracted.strip())
    return pages


def _stable_document_id(title: str, source_uri: str, content: str) -> str:
    raw_value = f"{title}:{source_uri}:{sha1(content.encode('utf-8')).hexdigest()}"
    return BaseEntity.build_stable_id("document", raw_value)


@dataclass(frozen=True)
class DocumentIngestionService:
    repository: KnowledgeRepositoryPort

    def ingest(self, request: DocumentIngestRequest) -> dict[str, object]:
        source_uri = request.source_uri or request.pdf_path or "memory://document"
        pages = self._extract_pages(request)
        if not pages:
            raise ValueError("Document did not contain any extractable text")

        full_text = "\n\n".join(page_text for page_text in pages if page_text.strip())
        if not full_text.strip():
            raise ValueError("Document did not contain any extractable text")

        document_id = _stable_document_id(request.title, source_uri, full_text)
        page_count = len(pages)
        header_summary = full_text[:1200].strip()
        header_entry = KnowledgeEntry(
            id=document_id,
            title=request.title,
            content=header_summary,
            tags=self._base_tags(request.tags) + ["document", "index"],
            source_type="document",
            source_uri=source_uri,
            document_id=document_id,
            document_title=request.title,
            page_number=None,
            chunk_index=None,
            chunk_count=None,
            source_chars=len(full_text),
            embedding=_embedding_from_tokens(_tokenize(full_text)),
        )
        saved_document = self.repository.save(header_entry)

        chunk_records: list[KnowledgeEntry] = []
        chunk_counter = 0
        for page_number, page_text in enumerate(pages, start=1):
            for chunk_text in _chunk_words(page_text, chunk_size=request.chunk_size, overlap=request.chunk_overlap):
                tokens = _tokenize(chunk_text)
                chunk_entry = KnowledgeEntry(
                    id=BaseEntity.build_stable_id("document_chunk", f"{document_id}:{chunk_counter}"),
                    title=f"{request.title} :: p{page_number} #{chunk_counter + 1}",
                    content=chunk_text,
                    tags=self._base_tags(request.tags) + ["document", "chunk", f"page:{page_number}"],
                    source_type="document_chunk",
                    source_uri=source_uri,
                    document_id=document_id,
                    document_title=request.title,
                    page_number=page_number,
                    chunk_index=chunk_counter,
                    chunk_count=None,
                    source_chars=len(chunk_text),
                    embedding=_embedding_from_tokens(tokens),
                )
                saved_chunk = self.repository.save(chunk_entry)
                chunk_records.append(saved_chunk)
                chunk_counter += 1

        if chunk_records:
            self._touch_document_chunk_count(saved_document, len(chunk_records))

        return {
            "document": saved_document.as_dict(),
            "chunks": [chunk.as_dict() for chunk in chunk_records],
            "page_count": page_count,
            "chunk_count": len(chunk_records),
        }

    def list_documents(self, request: DocumentListRequest) -> list[dict[str, object]]:
        if request.limit <= 0:
            return []

        documents = [entry for entry in self.repository.list_all() if entry.source_type == "document"]
        documents.sort(key=lambda entry: (entry.created_at or entry.updated_at), reverse=True)
        return [document.as_dict() for document in documents[: request.limit]]

    def overview(self, request: DocumentOverviewRequest) -> dict[str, object]:
        all_entries = self.repository.list_all()
        documents = [entry for entry in all_entries if entry.source_type == "document"]
        chunks = [entry for entry in all_entries if entry.source_type == "document_chunk"]
        documents.sort(key=lambda entry: (entry.created_at or entry.updated_at), reverse=True)
        chunks.sort(key=lambda entry: (entry.created_at or entry.updated_at), reverse=True)
        return {
            "document_count": len(documents),
            "chunk_count": len(chunks),
            "recent_documents": [document.as_dict() for document in documents[: request.limit]],
            "recent_chunks": [chunk.as_dict() for chunk in chunks[: request.limit]],
        }

    def _extract_pages(self, request: DocumentIngestRequest) -> list[str]:
        if request.pdf_path:
            pdf_path = Path(request.pdf_path)
            if not pdf_path.exists():
                raise FileNotFoundError(f"PDF not found: {pdf_path}")
            pages = _read_pdf_pages(str(pdf_path))
            return pages

        if request.raw_text is not None:
            return [request.raw_text]

        raise ValueError("Either raw_text or pdf_path must be provided")

    @staticmethod
    def _base_tags(tags: tuple[str, ...]) -> list[str]:
        return [tag for tag in tags if tag]

    def _touch_document_chunk_count(self, document: KnowledgeEntry, chunk_count: int) -> None:
        document.chunk_count = chunk_count
        document.touch()
        self.repository.save(document)