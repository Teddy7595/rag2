from __future__ import annotations

from pathlib import Path


def _word_count(text: str) -> int:
    return len(text.split())


class LocalTokenizerRuntime:
    """Counts tokens against the real vocabulary of a local GGUF model.

    Loads the model with `vocab_only=True` so only the tokenizer is read into
    memory, independent of which backend (local GGUF or Ollama) is active for
    chat generation, with no network access and no model-weight cost.
    """

    def __init__(self, models_dir: Path, *, model_path: Path | None = None) -> None:
        self._models_dir = models_dir
        self._explicit_model_path = model_path
        self._llama: object | None = None
        self._load_attempted = False

    def count_tokens(self, text: str) -> int:
        if not text:
            return 0
        llama = self._load()
        if llama is None:
            return _word_count(text)
        try:
            tokens = llama.tokenize(text.encode("utf-8"), add_bos=False, special=False)
            return len(tokens)
        except Exception:
            return _word_count(text)

    def _load(self) -> object | None:
        if self._llama is not None:
            return self._llama
        if self._load_attempted:
            return None
        self._load_attempted = True

        model_path = self._resolve_model_path()
        if model_path is None:
            return None

        try:
            from llama_cpp import Llama
        except ImportError:
            return None

        try:
            self._llama = Llama(model_path=str(model_path), vocab_only=True, verbose=False)
        except Exception:
            self._llama = None
        return self._llama

    def _resolve_model_path(self) -> Path | None:
        if self._explicit_model_path is not None and self._explicit_model_path.is_file():
            return self._explicit_model_path
        if not self._models_dir.exists():
            return None
        return next(self._models_dir.rglob("*.gguf"), None)
