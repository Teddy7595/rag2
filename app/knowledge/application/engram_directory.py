from __future__ import annotations

import re

from app.knowledge.domain import Identity


class EngramDirectory:
    def __init__(self) -> None:
        self.identity_store: dict[str, Identity] = {}
        self.last_active_identity_id = "DEFAULT"

    def reset(self) -> None:
        self.identity_store = {}
        self.last_active_identity_id = "DEFAULT"

    def cache(self, identity: Identity) -> None:
        key_name = identity.name or str(identity.id) or "UNKNOWN"
        self.identity_store[key_name] = identity
        if identity.id:
            self.identity_store[str(identity.id)] = identity

    def replace(self, identity: Identity) -> None:
        self.remove(str(identity.id))
        self.cache(identity)

    def remove(self, identity_id: str) -> None:
        key = str(identity_id)
        keys_to_remove = [store_key for store_key, value in self.identity_store.items() if str(value.id) == key]
        for store_key in keys_to_remove:
            self.identity_store.pop(store_key, None)

        if self.last_active_identity_id == key:
            remaining_identities = self._iter_unique_identities()
            self.last_active_identity_id = str(remaining_identities[-1].id) if remaining_identities else "DEFAULT"

    def has_identity_id(self, identity_id: str) -> bool:
        return str(identity_id) in self.identity_store

    def get_by_id(self, identity_id: str) -> Identity | None:
        return self.identity_store.get(str(identity_id))

    def ensure_default_identity(self) -> None:
        if self.identity_store:
            return
        self.identity_store["DEFAULT"] = self._default_identity()
        self.last_active_identity_id = "DEFAULT"

    def current_identity(self) -> Identity:
        identity = self.get_by_id(self.last_active_identity_id)
        if identity:
            return identity

        unique_identities = self._iter_unique_identities()
        if unique_identities:
            return unique_identities[-1]

        return self._default_identity()

    def resolve(self, raw_text: str, identity_id: str | None = None) -> tuple[Identity, str]:
        target_id = identity_id if identity_id else self.last_active_identity_id
        cleaned_text = raw_text

        match = re.search(r"@(\w+)", raw_text)
        if match:
            name_ref = match.group(1)
            for identity in self._iter_unique_identities():
                if name_ref.lower() in identity.name.lower():
                    target_id = str(identity.id)
                    cleaned_text = cleaned_text.replace(f"@{name_ref}", "", 1)
                    break

        identity = self.get_by_id(target_id) or self.current_identity()
        self.last_active_identity_id = str(identity.id) if identity.id else target_id
        cleaned_text = re.sub(r"\s+", " ", cleaned_text).strip()
        return identity, cleaned_text

    def resolve_owner_name(self, raw_owner: str) -> str:
        if raw_owner in self.identity_store:
            return self.identity_store[raw_owner].name
        if raw_owner == "user":
            return "user"
        return raw_owner or "System"

    def list_hint_handles(self) -> list[str]:
        return [identity.hint_handle() for identity in self._iter_unique_identities()]

    def list_engrams(self) -> list[Identity]:
        return list(self._iter_unique_identities())

    def _iter_unique_identities(self) -> list[Identity]:
        unique_ids: set[str] = set()
        identities: list[Identity] = []

        for identity in self.identity_store.values():
            identity_id = str(identity.id)
            if identity_id in unique_ids or identity_id in {"DEFAULT", "ERR", "SETUP"}:
                continue
            unique_ids.add(identity_id)
            identities.append(identity)

        return identities

    def _default_identity(self) -> Identity:
        return Identity(
            id="DEFAULT",
            name="System",
            avatar="",
            color_hex="#6b7280",
            intellectual_profile="General",
            behavior_prompt="",
            meta_rule="Stay consistent with the selected identity.",
            moral_threshold=0,
            interaction_mode="Directo",
            dialogue_examples=[],
            backstory="",
            temperatura_base=0.8,
            top_p_base=1.0,
            max_tokens_respuesta=2048,
        )