from __future__ import annotations

from pathlib import Path

from app.core.settings import load_settings
from app.models.runtime_service import LocalInferenceService
from app.models.service import ModelCatalogService


def build_catalog_service(tmp_path: Path, monkeypatch) -> ModelCatalogService:
    vault_dir = tmp_path / "vault"
    ai_model_dir = tmp_path / "ai_models"
    monkeypatch.setenv("VAULT_DIR", str(vault_dir))
    monkeypatch.setenv("AI_MODEL_DIR", str(ai_model_dir))
    monkeypatch.setenv("AI_MODELS_DIR", str(ai_model_dir))
    settings = load_settings(tmp_path)
    return ModelCatalogService(settings)


def test_normalize_runtime_config_defaults_max_tokens_to_3072_when_missing() -> None:
    catalog_service = object.__new__(ModelCatalogService)
    normalized = catalog_service._normalize_runtime_config({})
    assert normalized["text_generation_max_tokens"] == 3072


def test_normalize_runtime_config_preserves_explicit_max_tokens() -> None:
    catalog_service = object.__new__(ModelCatalogService)
    normalized = catalog_service._normalize_runtime_config({"text_generation_max_tokens": 2048})
    assert normalized["text_generation_max_tokens"] == 2048


class FakeCatalogService:
    def __init__(self, runtime_config: dict[str, object]) -> None:
        self._runtime_config = runtime_config

    def catalog(self) -> dict[str, object]:
        return {"runtime_config": self._runtime_config}


def test_generation_defaults_returns_3072_when_config_has_no_max_tokens() -> None:
    service = LocalInferenceService(catalog_service=FakeCatalogService({}))
    assert service.generation_defaults()["max_tokens"] == 3072


def test_generation_defaults_reflects_persisted_max_tokens() -> None:
    service = LocalInferenceService(catalog_service=FakeCatalogService({"text_generation_max_tokens": 3072}))
    assert service.generation_defaults()["max_tokens"] == 3072


def test_normalize_profile_clamps_out_of_range_params(tmp_path: Path, monkeypatch) -> None:
    catalog_service = build_catalog_service(tmp_path, monkeypatch)
    normalized = catalog_service._normalize_profile(
        {"name": "Extreme", "kind": "text", "params": {"text_generation_temperature": 99.0, "llama_cpp_n_ctx": 1}}
    )
    assert normalized["params"]["text_generation_temperature"] == 2.0
    assert normalized["params"]["llama_cpp_n_ctx"] == 512


def test_create_update_delete_profile_round_trip(tmp_path: Path, monkeypatch) -> None:
    catalog_service = build_catalog_service(tmp_path, monkeypatch)

    created = catalog_service.create_profile(
        {"name": "Creative-8k", "kind": "text", "params": {"text_generation_temperature": 0.7, "llama_cpp_n_ctx": 8192}}
    )
    assert created["name"] == "Creative-8k"
    assert created["params"]["llama_cpp_n_ctx"] == 8192

    profiles = catalog_service.load_profiles()["profiles"]
    assert len(profiles) == 1

    updated = catalog_service.update_profile(created["id"], {"params": {"text_generation_temperature": 0.9}})
    assert updated is not None
    assert updated["params"]["text_generation_temperature"] == 0.9
    assert updated["params"]["llama_cpp_n_ctx"] == 8192  # untouched keys survive the merge

    assert catalog_service.delete_profile(created["id"]) is True
    assert catalog_service.load_profiles()["profiles"] == []
    assert catalog_service.delete_profile(created["id"]) is False


def test_set_bundle_profile_enforces_one_profile_per_bundle_per_kind(tmp_path: Path, monkeypatch) -> None:
    catalog_service = build_catalog_service(tmp_path, monkeypatch)
    profile_a = catalog_service.create_profile({"name": "A", "kind": "text", "params": {}})
    profile_b = catalog_service.create_profile({"name": "B", "kind": "text", "params": {}})

    catalog_service.set_bundle_profile("text", "bundle-x", profile_a["id"])
    assert catalog_service.resolve_profile_for_bundle("text", "bundle-x")["id"] == profile_a["id"]

    catalog_service.set_bundle_profile("text", "bundle-x", profile_b["id"])
    resolved = catalog_service.resolve_profile_for_bundle("text", "bundle-x")
    assert resolved["id"] == profile_b["id"]

    profiles_by_id = {p["id"]: p for p in catalog_service.load_profiles()["profiles"]}
    assert "bundle-x" not in profiles_by_id[profile_a["id"]]["assigned_bundle_ids"]


def test_update_selection_applies_assigned_profile_on_bundle_switch(tmp_path: Path, monkeypatch) -> None:
    catalog_service = build_catalog_service(tmp_path, monkeypatch)
    (catalog_service.models_dir / "model-a.gguf").write_bytes(b"fake-gguf")
    (catalog_service.models_dir / "model-b.gguf").write_bytes(b"fake-gguf")
    bundle_ids = {bundle.display_name: bundle.bundle_id for bundle in catalog_service.discover_bundles()}
    bundle_a_id = next(bid for name, bid in bundle_ids.items() if "model-a" in bid)
    bundle_b_id = next(bid for name, bid in bundle_ids.items() if "model-b" in bid)

    profile = catalog_service.create_profile(
        {"name": "Custom", "kind": "text", "params": {"text_generation_max_tokens": 999}}
    )
    catalog_service.set_bundle_profile("text", bundle_b_id, profile["id"])

    catalog_service.update_selection({"text_provider": "local", "text_bundle_id": bundle_a_id})
    baseline_max_tokens = catalog_service.load_runtime_config()["text_generation_max_tokens"]
    assert baseline_max_tokens != 999

    catalog_service.update_selection({"text_provider": "local", "text_bundle_id": bundle_b_id})
    assert catalog_service.load_runtime_config()["text_generation_max_tokens"] == 999

    # Switching to a bundle with no assigned profile leaves the current config untouched.
    catalog_service.update_selection({"text_provider": "local", "text_bundle_id": bundle_a_id})
    assert catalog_service.load_runtime_config()["text_generation_max_tokens"] == 999


def test_set_bundle_profile_applies_config_immediately_when_bundle_is_active(tmp_path: Path, monkeypatch) -> None:
    catalog_service = build_catalog_service(tmp_path, monkeypatch)
    (catalog_service.models_dir / "active-model.gguf").write_bytes(b"fake-gguf")
    bundle_id = catalog_service.discover_bundles()[0].bundle_id
    catalog_service.update_selection({"text_provider": "local", "text_bundle_id": bundle_id})

    profile = catalog_service.create_profile(
        {"name": "Active-profile", "kind": "text", "params": {"text_generation_max_tokens": 777}}
    )
    assert catalog_service.load_runtime_config()["text_generation_max_tokens"] != 777

    catalog_service.set_bundle_profile("text", bundle_id, profile["id"])
    assert catalog_service.load_runtime_config()["text_generation_max_tokens"] == 777


def test_set_bundle_profile_does_not_apply_when_bundle_is_not_active(tmp_path: Path, monkeypatch) -> None:
    catalog_service = build_catalog_service(tmp_path, monkeypatch)
    (catalog_service.models_dir / "active-model.gguf").write_bytes(b"fake-gguf")
    (catalog_service.models_dir / "other-model.gguf").write_bytes(b"fake-gguf")
    bundles = {b.display_name: b.bundle_id for b in catalog_service.discover_bundles()}
    active_id = next(bid for name, bid in bundles.items() if "active-model" in bid)
    other_id = next(bid for name, bid in bundles.items() if "other-model" in bid)
    catalog_service.update_selection({"text_provider": "local", "text_bundle_id": active_id})

    profile = catalog_service.create_profile(
        {"name": "Inactive-profile", "kind": "text", "params": {"text_generation_max_tokens": 777}}
    )
    baseline = catalog_service.load_runtime_config()["text_generation_max_tokens"]
    catalog_service.set_bundle_profile("text", other_id, profile["id"])
    assert catalog_service.load_runtime_config()["text_generation_max_tokens"] == baseline


def test_update_profile_reapplies_config_when_assigned_to_active_bundle(tmp_path: Path, monkeypatch) -> None:
    catalog_service = build_catalog_service(tmp_path, monkeypatch)
    (catalog_service.models_dir / "active-model.gguf").write_bytes(b"fake-gguf")
    bundle_id = catalog_service.discover_bundles()[0].bundle_id
    catalog_service.update_selection({"text_provider": "local", "text_bundle_id": bundle_id})

    profile = catalog_service.create_profile(
        {"name": "Edited-profile", "kind": "text", "params": {"text_generation_max_tokens": 500}}
    )
    catalog_service.set_bundle_profile("text", bundle_id, profile["id"])
    assert catalog_service.load_runtime_config()["text_generation_max_tokens"] == 500

    catalog_service.update_profile(profile["id"], {"params": {"text_generation_max_tokens": 1234}})
    assert catalog_service.load_runtime_config()["text_generation_max_tokens"] == 1234


def test_is_bundle_active_reflects_current_selection(tmp_path: Path, monkeypatch) -> None:
    catalog_service = build_catalog_service(tmp_path, monkeypatch)
    (catalog_service.models_dir / "active-model.gguf").write_bytes(b"fake-gguf")
    (catalog_service.models_dir / "other-model.gguf").write_bytes(b"fake-gguf")
    bundles = {b.display_name: b.bundle_id for b in catalog_service.discover_bundles()}
    active_id = next(bid for name, bid in bundles.items() if "active-model" in bid)
    other_id = next(bid for name, bid in bundles.items() if "other-model" in bid)
    catalog_service.update_selection({"text_provider": "local", "text_bundle_id": active_id})

    assert catalog_service.is_bundle_active("text", active_id) is True
    assert catalog_service.is_bundle_active("text", other_id) is False
