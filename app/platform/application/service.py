from __future__ import annotations

from app.platform.domain import ModuleProfile


class PlatformService:
    def __init__(self) -> None:
        self.profile = ModuleProfile(
            name="platform",
            summary="Core runtime shell",
            stage="alpha",
        )

    def describe(self) -> ModuleProfile:
        return self.profile

    def health(self) -> dict[str, object]:
        return {
            "status": "ok",
            **self.profile.as_dict(),
        }