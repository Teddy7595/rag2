from __future__ import annotations

from dataclasses import dataclass
import base64
from collections.abc import Callable
from hashlib import sha1
from pathlib import Path
import re

from pypdf import PdfReader

from app.core.base_entity import BaseEntity
from app.knowledge.application.embedding_runtime import SemanticEmbeddingRuntime
from app.knowledge.application.ports import KnowledgeRepositoryPort
from app.knowledge.application.tokenizer_runtime import LocalTokenizerRuntime
from app.knowledge.domain import KnowledgeEntry
from app.knowledge.events import DocumentIngestRequest, DocumentListRequest, DocumentOverviewRequest


def _clean_ingested_text(raw_text: str) -> str:
    text = raw_text.replace("\ufeff", " ")
    text = re.sub(r"```[\s\S]*?```", " ", text)
    text = re.sub(r"`{1,3}", " ", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)
    text = re.sub(r"\[[^\]]*\]\([^)]*\)", " ", text)
    text = re.sub(r"(^|\s)[*_~#>{2,}|]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÑ0-9¿¡\"'])|\n{2,}")


def _split_sentences(text: str) -> list[str]:
    stripped = text.strip()
    if not stripped:
        return []
    return [sentence.strip() for sentence in _SENTENCE_SPLIT_RE.split(stripped) if sentence.strip()]


def _default_count_tokens(text: str) -> int:
    return len(text.split())


def _chunk_words(
    text: str,
    *,
    chunk_size: int,
    overlap: int,
    count_tokens: Callable[[str], int] = _default_count_tokens,
) -> list[str]:
    """Pack whole sentences into chunks up to `chunk_size` tokens (as counted by
    `count_tokens`), never splitting mid-sentence.

    `count_tokens` defaults to a plain word count; callers pass a real
    tokenizer (e.g. `LocalTokenizerRuntime.count_tokens`) to size chunks
    against actual model tokens instead of words.

    Falls back to a hard word-window split only for a single sentence that alone
    exceeds `chunk_size` (rare, but avoids an unbounded chunk for run-on text).
    """
    safe_chunk_size = max(1, chunk_size)
    safe_overlap = max(0, min(overlap, safe_chunk_size - 1))

    sentences = _split_sentences(text)
    if not sentences:
        return []

    chunks: list[str] = []
    current_sentences: list[str] = []
    current_token_count = 0

    def flush() -> None:
        if current_sentences:
            chunks.append(" ".join(current_sentences).strip())

    for sentence in sentences:
        sentence_words = sentence.split()
        if not sentence_words:
            continue
        sentence_token_count = count_tokens(sentence)

        if sentence_token_count > safe_chunk_size:
            flush()
            current_sentences = []
            current_token_count = 0
            start = 0
            while start < len(sentence_words):
                end = min(len(sentence_words), start + safe_chunk_size)
                piece = " ".join(sentence_words[start:end]).strip()
                if piece:
                    chunks.append(piece)
                if end >= len(sentence_words):
                    break
                start = end - safe_overlap
            continue

        if current_token_count + sentence_token_count > safe_chunk_size and current_sentences:
            flush()
            if safe_overlap > 0:
                overlap_words = " ".join(current_sentences).split()[-safe_overlap:]
                current_sentences = [" ".join(overlap_words)] if overlap_words else []
                current_token_count = count_tokens(current_sentences[0]) if current_sentences else 0
            else:
                current_sentences = []
                current_token_count = 0

        current_sentences.append(sentence)
        current_token_count += sentence_token_count

    flush()
    return [chunk for chunk in chunks if chunk]


def _read_pdf_pages(pdf_path: str) -> list[str]:
    reader = PdfReader(pdf_path)
    pages: list[str] = []
    for page in reader.pages:
        extracted = _clean_ingested_text(page.extract_text() or "")
        pages.append(extracted.strip())
    return pages


def _read_pdf_image_metadata(pdf_path: str) -> list[dict[str, object]]:
    reader = PdfReader(pdf_path)
    payload: list[dict[str, object]] = []
    for page_index, page in enumerate(reader.pages, start=1):
        images = getattr(page, "images", [])
        for image_index, image in enumerate(images, start=1):
            name = str(getattr(image, "name", f"image_{page_index}_{image_index}"))
            data = getattr(image, "data", None)
            size = len(data) if isinstance(data, (bytes, bytearray)) else 0
            data_base64 = ""
            if isinstance(data, (bytes, bytearray)) and 0 < size <= 2_000_000:
                data_base64 = base64.b64encode(bytes(data)).decode("ascii")

            extension = Path(name).suffix.lower().lstrip(".")
            if not extension:
                extension = "png"
            payload.append(
                {
                    "page_number": page_index,
                    "image_index": image_index,
                    "name": name,
                    "bytes": size,
                    "extension": extension,
                    "data_base64": data_base64,
                }
            )
    return payload


def _stable_document_id(title: str, source_uri: str, content: str) -> str:
    raw_value = f"{title}:{source_uri}:{sha1(content.encode('utf-8')).hexdigest()}"
    return BaseEntity.build_stable_id("document", raw_value)


@dataclass(frozen=True)
class DocumentIngestionService:
    repository: KnowledgeRepositoryPort
    embedding_runtime: SemanticEmbeddingRuntime
    tokenizer_runtime: LocalTokenizerRuntime | None = None

    def ingest(self, request: DocumentIngestRequest) -> dict[str, object]:
        source_uri = request.source_uri or request.pdf_path or "memory://document"
        pages = self._extract_pages(request)
        image_artifacts = self._extract_pdf_images(request)
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
            embedding=self.embedding_runtime.embed_text(full_text),
        )
        saved_document = self.repository.save(header_entry)

        count_tokens = self.tokenizer_runtime.count_tokens if self.tokenizer_runtime else _default_count_tokens

        chunk_records: list[KnowledgeEntry] = []
        chunk_counter = 0
        for page_number, page_text in enumerate(pages, start=1):
            for chunk_text in _chunk_words(
                page_text,
                chunk_size=request.chunk_size,
                overlap=request.chunk_overlap,
                count_tokens=count_tokens,
            ):
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
                    embedding=self.embedding_runtime.embed_text(chunk_text),
                )
                saved_chunk = self.repository.save(chunk_entry)
                chunk_records.append(saved_chunk)
                chunk_counter += 1

        if chunk_records:
            self._touch_document_chunk_count(saved_document, len(chunk_records))

        image_records: list[KnowledgeEntry] = []
        for artifact in image_artifacts:
            page_number = int(artifact.get("page_number") or 0)
            image_index = int(artifact.get("image_index") or 0)
            image_name = str(artifact.get("name") or f"image_{page_number}_{image_index}")
            byte_size = int(artifact.get("bytes") or 0)
            content = f"PDF image artifact '{image_name}' on page {page_number} ({byte_size} bytes)."
            image_entry = KnowledgeEntry(
                id=BaseEntity.build_stable_id("document_image", f"{document_id}:{page_number}:{image_index}:{image_name}"),
                title=f"{request.title} :: image p{page_number} #{image_index}",
                content=content,
                tags=self._base_tags(request.tags) + ["document", "image", f"page:{page_number}"],
                source_type="document_image",
                source_uri=source_uri,
                document_id=document_id,
                document_title=request.title,
                page_number=page_number,
                chunk_index=image_index,
                chunk_count=None,
                source_chars=len(content),
                embedding=self.embedding_runtime.embed_text(content),
            )
            image_records.append(self.repository.save(image_entry))

        return {
            "document": saved_document.as_dict(),
            "chunks": [chunk.as_dict() for chunk in chunk_records],
            "images": [image.as_dict() for image in image_records],
            "page_count": page_count,
            "chunk_count": len(chunk_records),
            "image_count": len(image_records),
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
            return [_clean_ingested_text(request.raw_text)]

        raise ValueError("Either raw_text or pdf_path must be provided")

    @staticmethod
    def _base_tags(tags: tuple[str, ...]) -> list[str]:
        return [tag for tag in tags if tag]

    @staticmethod
    def _extract_pdf_images(request: DocumentIngestRequest) -> list[dict[str, object]]:
        if not request.pdf_path:
            return []
        pdf_path = Path(request.pdf_path)
        if not pdf_path.exists():
            return []
        try:
            return _read_pdf_image_metadata(str(pdf_path))
        except Exception:
            return []

    def _touch_document_chunk_count(self, document: KnowledgeEntry, chunk_count: int) -> None:
        document.chunk_count = chunk_count
        document.touch()
        self.repository.save(document)