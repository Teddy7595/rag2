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

## AMD GPU: use ./run.sh instead of `uv sync` / `uv run`

If you set up the local AMD GPU runtime (below), **do not run `uv sync` or `uv run` directly** once the initial install is done. `llama-cpp-python` is a plain dependency in `pyproject.toml` with no build flags, so any `uv sync` (including the implicit one `uv run` does by default) silently reinstalls a CPU-only build and discards the GPU backend (Vulkan on openSUSE, HIP on Arch) compiled by the installer — with no error.

Instead, start the app with:

```bash
./run.sh
```

It launches `main.py` directly through the venv's own Python (never through `uv run`), and if it detects the GPU backend `.so` is missing (e.g. because something ran `uv sync` since the last start), it recompiles `llama-cpp-python` with the right flags for your distro before booting.

## AMD ROCm Setup

For an AMD-only machine, use the installer matching your distro:

```bash
./installer-arch.sh       # Arch Linux and derivatives (pacman)
./installer-opensuse.sh   # openSUSE Tumbleweed (zypper)
```

Both scripts:

- Install the build toolchain, ROCm runtime, and `uv`.
- Detect `AMD_GPU_TARGET` using `rocminfo` (or respect your exported value).
- Persist ROCm environment variables (`ROCM_PATH`, `HIP_PATH`, `HSA_OVERRIDE_GFX_VERSION`, `LD_LIBRARY_PATH`) for `bash` and `fish`.
- Install `torch`/`torchvision`/`sentence-transformers` from the prebuilt ROCm wheel index, scoped to the project's `.venv` (nothing is installed into the system Python).
- Compile `llama-cpp-python` from source, scoped to the same `.venv`, and verify it reports GPU offload support before finishing.

They differ only in the `llama-cpp-python` GPU backend, because of how each distro packages ROCm:

- **Arch** (`installer-arch.sh`): compiles with the native HIP backend (`-DGGML_HIP=ON`), since `rocm-hip-sdk` bundles hipBLAS/rocBLAS.
- **openSUSE** (`installer-opensuse.sh`): compiles with the Vulkan backend (`-DGGML_VULKAN=ON`), since Tumbleweed does not package hipBLAS/rocBLAS. Vulkan performs comparably on RDNA3 and needs no ROCm math libraries — `vulkan-devel` and `shaderc` (for `glslc`) are enough.

Only the `llama-cpp-python` build differs; `torch`/`sentence-transformers` still run on ROCm on both distros, since PyPI ships self-contained ROCm wheels that don't depend on system hipBLAS.

If you need to override defaults on either script:

```bash
AMD_GPU_TARGET=gfx1100 HSA_OVERRIDE_GFX_VERSION=11.0.0 ./installer-opensuse.sh
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

The HTML views are centralized in `app/adapters/web`, while storage and models keep the API surface. The web module exposes the landing page, the local admin panel, the route visualizer, and the model catalog at:

```text
/
/admin
/admin/routes
/admin/models
/admin/runtime-ai
/ui
/ui-assets
```

The minimal vanilla reference bundle lives in `frontend/dist` and is served directly from `/ui-assets/`.
Compiled frontend builds can be mounted under `WEB_FRONTEND_MOUNT_PATH` and served from `WEB_FRONTEND_DIR`.
The shell page at `/ui` can be used as the landing point for Angular, Vite, or vanilla frontend bundles and can inject extra assets through `WEB_FRONTEND_STYLES` and `WEB_FRONTEND_SCRIPTS`.

The admin portal now includes an AI runtime diagnostics page at `/admin/runtime-ai` with local text and vision smoke tests, and the `/chat` page can upload an image to exercise the local vision runtime.

Local inference uses `llama-cpp-python` when available in the runtime environment. The models module keeps the local runtime optional and reports its binding/version state through `/api/models/runtime/status`.

The storage slice keeps the storage endpoints at:

```text
/api/storage/overview
/public
/uploads
```

The admin area also includes a route visualizer with a NestJS-style module tree for the registered HTTP, websocket, and static mount routes.

The local AI model catalog scans `ai_models/` recursively, groups GGUF files into bundles, and exposes a selector for local text/vision bundles plus Ollama and LM Studio configuration.
You can point `APP_CONVERSATION_INTENT_BUNDLE_ID` to a smaller local GGUF bundle to classify user intent on CPU with a short prompt, while keeping the main chat model unchanged.

Security policy is configured with local-only admin access, a simple in-memory rate limit, and an optional ban list via `APP_ADMIN_LOCAL_ONLY`, `APP_RATE_LIMIT_WINDOW_SECONDS`, `APP_RATE_LIMIT_MAX_REQUESTS`, and `APP_BAN_LIST`.

The knowledge and operations modules expose their own module routes under:

```text
/api/knowledge/*
/api/operations/*
/api/models/*
```

Additional coherence endpoints now available:

- `POST /api/knowledge/context/graph`: builds a context graph (query, identity, engram and knowledge nodes/edges) with primary and secondary topics.
- `GET /api/operations/sagas?statuses=completed,active`: filters sagas by status.
- `POST /api/operations/sagas/{saga_id}/debate`: records debate iterations and can persist inspirational memory items tagged by saga and engram.

This allows closed or active sagas to remain editable and extensible while feeding retrieval memory for future prompts under the same engram persona.

## Database

The default local database is SQLite under `.vault/rag2.sqlite3` when `DATABASE_URL` is empty.
Set `DATABASE_URL` to a PostgreSQL URL when you want server-backed persistence.

Core database wiring lives in `app/core/database/` and stays database-agnostic.

## Local Directories

- `.vault/` stores private runtime artifacts and should stay local.
- `.vault/public/` is mounted at `/public` for public static assets.
- `.vault/uploads/` is mounted at `/uploads` for local runtime uploads.
- `ai_model/` stores local model assets and caches.
