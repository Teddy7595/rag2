"""One-off operational aid: list which local GGUF bundles have an embedded
tokenizer.chat_template and which don't. Not imported by the app — run manually:

    uv run --isolated --with gguf scripts/inspect_chat_templates.py ai_models

(--isolated matters: plain `uv run` syncs this project's own .venv first, which
silently reinstalls llama-cpp-python without its GPU build flags and wipes the
compiled backend .so — --isolated runs in a throwaway env instead.)

Models without an embedded template fall back to the legacy plain-text prompt
lead-in at generation time (see app/models/chat_template.py); this script is
just for auditing that fallback surface, not for fixing it automatically.
"""
from __future__ import annotations

import sys
from pathlib import Path

from gguf import GGUFReader


def main() -> None:
    models_dir = Path(sys.argv[1] if len(sys.argv) > 1 else "ai_models")
    gguf_paths = sorted(models_dir.glob("*.gguf"))
    if not gguf_paths:
        print(f"No .gguf files found in {models_dir}")
        return

    for gguf_path in gguf_paths:
        try:
            reader = GGUFReader(str(gguf_path))
        except Exception as exc:
            print(f"{gguf_path.name}: ERROR opening ({exc})")
            continue
        field = reader.fields.get("tokenizer.chat_template")
        status = "present" if field is not None and field.data else "MISSING"
        print(f"{gguf_path.name}: chat_template={status}")


if __name__ == "__main__":
    main()
