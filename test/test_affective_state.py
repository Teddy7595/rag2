from __future__ import annotations

from pathlib import Path

from app.knowledge.application.service import _compute_affective_delta
from app.knowledge.domain import AffectiveState
from app.knowledge.events import AffectiveStateGetRequest, AffectiveStateUpdateRequest
from test.test_integration import build_test_app


def test_compute_affective_delta_positive_message_moves_pleasure_up() -> None:
    delta_p, _delta_a, _delta_d = _compute_affective_delta("Que genial, me encanta esto, gracias!", "ok", 100)
    assert delta_p > 0


def test_compute_affective_delta_negative_message_moves_pleasure_down() -> None:
    delta_p, _delta_a, _delta_d = _compute_affective_delta("Esto es terrible, odio este error.", "ok", 100)
    assert delta_p < 0


def test_compute_affective_delta_exclamations_increase_arousal() -> None:
    _delta_p, delta_a, _delta_d = _compute_affective_delta("Increible!!! Vamos!!!", "ok", 100)
    assert delta_a > 0


def test_compute_affective_delta_stays_within_bounds() -> None:
    noisy_text = " ".join(["genial", "excelente", "increible", "encanta", "feliz"] * 5) + "!!!!!!"
    delta_p, delta_a, delta_d = _compute_affective_delta(noisy_text, "x" * 5000, 10)
    for delta in (delta_p, delta_a, delta_d):
        assert -0.15 <= delta <= 0.15


def test_affective_state_repository_round_trip(tmp_path: Path, monkeypatch) -> None:
    app = build_test_app(tmp_path, monkeypatch)
    repository = app.state.context.services["knowledge"].affective_state_repository

    assert repository.get("engram-x") is None

    saved = repository.upsert(AffectiveState(engram_id="engram-x", pleasure=0.4, arousal=-0.2, dominance=0.1))
    assert saved.pleasure == 0.4

    fetched = repository.get("engram-x")
    assert fetched is not None
    assert fetched.pleasure == 0.4
    assert fetched.arousal == -0.2
    assert fetched.dominance == 0.1


def test_update_affective_state_decays_toward_baseline_on_neutral_turns(tmp_path: Path, monkeypatch) -> None:
    app = build_test_app(tmp_path, monkeypatch)
    knowledge_service = app.state.context.services["knowledge"]

    knowledge_service.affective_state_repository.upsert(
        AffectiveState(engram_id="engram-y", pleasure=0.8, arousal=0.8, dominance=0.8)
    )

    for _ in range(15):
        knowledge_service.update_affective_state(
            AffectiveStateUpdateRequest(engram_id="engram-y", user_text="ok", reply_text="ok", max_tokens=100)
        )

    state = knowledge_service.get_affective_state(AffectiveStateGetRequest(engram_id="engram-y"))
    assert abs(state["pleasure"]) < 0.2
    assert abs(state["arousal"]) < 0.2
    assert abs(state["dominance"]) < 0.2


def test_get_affective_state_defaults_to_zero_when_missing(tmp_path: Path, monkeypatch) -> None:
    app = build_test_app(tmp_path, monkeypatch)
    knowledge_service = app.state.context.services["knowledge"]

    state = knowledge_service.get_affective_state(AffectiveStateGetRequest(engram_id="never-seen"))
    assert state == {"engram_id": "never-seen", "pleasure": 0.0, "arousal": 0.0, "dominance": 0.0, "updated_at": None}
