"""One-off operational aid: re-embed every existing KnowledgeEntry with the
currently configured embedding runtime (see OLLAMA_EMBEDDING_MODEL /
APP_EMBEDDING_MODEL_DIR in .env). Not imported by the app — run manually:

    uv run --isolated python scripts/reembed_knowledge.py

Why this is needed: `_embedding_score` in context_pipeline.py compares
embeddings by vector length. Switching the embedding runtime (e.g. from the
64-d hash fallback to a real model served by Ollama) changes that length, so
entries embedded under the old runtime silently score 0 for semantic
similarity until they're re-embedded with the new one.
"""
from __future__ import annotations

from app.bootstrap import create_app


def main() -> None:
    app = create_app()
    knowledge_service = app.state.context.services["knowledge"]
    repository = knowledge_service.repository
    embedding_runtime = knowledge_service.embedding_runtime

    entries = repository.list_all()
    print(f"Re-embedding {len(entries)} knowledge entries with {type(embedding_runtime).__name__}...")

    updated = 0
    for entry in entries:
        entry.embedding = embedding_runtime.embed_text(entry.content)
        repository.save(entry)
        updated += 1
        if updated % 25 == 0:
            print(f"  {updated}/{len(entries)}")

    print(f"Done. Re-embedded {updated} entries.")


if __name__ == "__main__":
    main()
