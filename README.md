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

The storage slice adds a landing page, a local admin panel, and storage endpoints at:

```text
/
/admin
/admin/routes
/api/storage/overview
/public
/uploads
```

The admin area also includes a route visualizer with a NestJS-style module tree for the registered HTTP, websocket, and static mount routes.

Security policy is configured with local-only admin access, a simple in-memory rate limit, and an optional ban list via `APP_ADMIN_LOCAL_ONLY`, `APP_RATE_LIMIT_WINDOW_SECONDS`, `APP_RATE_LIMIT_MAX_REQUESTS`, and `APP_BAN_LIST`.

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
- `.vault/public/` is mounted at `/public` for public static assets.
- `.vault/uploads/` is mounted at `/uploads` for local runtime uploads.
- `ai_model/` stores local model assets and caches.
