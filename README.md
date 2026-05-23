# RAG2 Modular Monolith

Seed for a modular monolith based on explicit wiring and internal events.

## Structure

```text
main.py
.env
.env.example
.vault/
ai_model/
app/
	core/
		database/
	platform/
	interaction/
	knowledge/
	operations/
```

## Quick Start

```bash
cp .env.example .env
uv sync
uvicorn main:app --reload
```

The app also runs with:

```bash
python main.py
```

## First Endpoint

The initial module exposes a health check at:

```text
/api/platform/health
```

The interaction module also exposes message routes at:

```text
/api/interaction/messages
/api/interaction/summary
```

The knowledge and operations modules expose their own module routes under:

```text
/api/knowledge/*
/api/operations/*
```

## Database

The default local database is SQLite under `.vault/rag2.sqlite3` when `DATABASE_URL` is empty.
Set `DATABASE_URL` to a PostgreSQL URL when you want server-backed persistence.

Core database wiring lives in `app/core/database/` and stays database-agnostic.

## Local Directories

- `.vault/` stores private runtime artifacts and should stay local.
- `ai_model/` stores local model assets and caches.
