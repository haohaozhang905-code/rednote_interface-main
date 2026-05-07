from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from interface_layer.runtime.session_state import default_login

if TYPE_CHECKING:
    from interface_layer.runtime.base import RuntimeSession


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass
class SessionRecord:
    session_id: str
    purpose: str | None
    user_data_dir: str
    bound: bool = False
    token: str | None = None
    runtime: "RuntimeSession | None" = field(default=None, repr=False, compare=False)
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    @property
    def status(self) -> str:
        return "bound" if self.bound else "idle"

    def public_state(self) -> dict[str, Any]:
        runtime_state = self.runtime.snapshot() if self.runtime is not None else {"login": default_login(), "current_context": {}}
        result: dict[str, Any] = {
            "session_id": self.session_id,
            "status": self.status,
            "bound": self.bound,
            "login": runtime_state["login"],
            "current_context": runtime_state["current_context"],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        if self.purpose is not None:
            result["purpose"] = self.purpose
        return result

    def persistent_state(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "purpose": self.purpose,
            "user_data_dir": self.user_data_dir,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_persistent(cls, payload: dict[str, Any]) -> "SessionRecord":
        session_id = str(payload["session_id"])
        user_data_dir = str(payload["user_data_dir"])
        return cls(
            session_id=session_id,
            purpose=payload.get("purpose"),
            user_data_dir=user_data_dir,
            bound=False,
            token=None,
            created_at=str(payload.get("created_at") or _now()),
            updated_at=str(payload.get("updated_at") or _now()),
        )
