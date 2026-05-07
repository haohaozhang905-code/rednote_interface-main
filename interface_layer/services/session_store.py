from __future__ import annotations

import asyncio
import secrets
from contextlib import suppress
from pathlib import Path
from typing import Any

from interface_layer.runtime.base import RuntimeBackend, RuntimeBackendError
from interface_layer.runtime.error_mapper import to_interface_error

from .errors import InterfaceError
from .session_persistence import SessionPersistence
from .session_record import SessionRecord, _now


def _id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(8)}"


class SessionStore:
    def __init__(self, runtime: RuntimeBackend, *, profile_root: Path) -> None:
        self._runtime = runtime
        self._profile_root = profile_root
        self._persistence = SessionPersistence(profile_root)
        self._sessions: dict[str, SessionRecord] = {item.session_id: item for item in self._persistence.load()}
        self._lock = asyncio.Lock()

    def list_sessions(self, bound: bool | None = None, status: str | None = None) -> list[dict[str, Any]]:
        records = list(self._sessions.values())
        if bound is not None:
            records = [item for item in records if item.bound is bound]
        if status is not None:
            records = [item for item in records if item.status == status]
        return [item.public_state() for item in records]

    async def create_session(self, purpose: str | None) -> dict[str, Any]:
        session_id = _id("sess")
        session_dir = self._profile_root / session_id
        user_data_dir = session_dir / "profile"
        record = SessionRecord(
            session_id=session_id,
            purpose=purpose,
            user_data_dir=str(user_data_dir),
        )
        self._ensure_user_data_dir(record)
        try:
            record.runtime = await self._runtime.create_session(self._runtime_payload(record))
        except RuntimeBackendError as exc:
            raise to_interface_error(exc, operation="create_session") from exc
        self._sessions[session_id] = record
        self._save(record)
        data = {"session_id": session_id, "status": record.status}
        if purpose is not None:
            data["purpose"] = purpose
        return data

    def get(self, session_id: str) -> SessionRecord:
        try:
            return self._sessions[session_id]
        except KeyError as exc:
            raise InterfaceError("session_not_found") from exc

    async def bind(self, session_id: str) -> dict[str, Any]:
        async with self._lock:
            record = self.get(session_id)
            if record.bound:
                raise InterfaceError("session_busy")
            record.token = _id("btok")
            record.bound = True
            record.updated_at = _now()
            self._save(record)
            return {"session_id": session_id, "token": record.token, "status": record.status}

    def unbind(self, session_id: str, token: str) -> None:
        record = self.verify_token(session_id, token)
        record.bound = False
        record.token = None
        record.updated_at = _now()
        self._save(record)

    def force_unbind(self, session_id: str) -> None:
        record = self.get(session_id)
        record.bound = False
        record.token = None
        record.updated_at = _now()
        self._save(record)

    async def destroy(self, session_id: str) -> None:
        record = self.get(session_id)
        if record.bound:
            raise InterfaceError("session_busy")
        if record.runtime is not None:
            try:
                await record.runtime.close()
            except RuntimeBackendError as exc:
                raise to_interface_error(exc) from exc
            finally:
                record.runtime = None
        del self._sessions[session_id]
        self._persistence.delete(session_id)

    async def close(self) -> None:
        records = list(self._sessions.values())
        for record in records:
            if record.runtime is None:
                continue
            with suppress(Exception):
                await record.runtime.close()

    def verify_token(self, session_id: str, token: str) -> SessionRecord:
        record = self.get(session_id)
        if not record.bound or record.token != token:
            raise InterfaceError("invalid_session_token")
        return record

    async def run_login_action(self, session_id: str, request: Any) -> dict[str, Any]:
        record = self.verify_token(session_id, request.token)
        payload = request.model_dump(exclude_none=True)
        runtime = await self._runtime_for(record)
        try:
            login = await runtime.run_login_action(payload)
        except RuntimeBackendError as exc:
            raise to_interface_error(exc) from exc
        record.updated_at = _now()
        self._save(record)
        return login

    async def get_login_status(self, session_id: str, token: str | None = None) -> dict[str, Any]:
        record = self.get(session_id)
        if token:
            self.verify_token(session_id, token)
        runtime = await self._runtime_for(record)
        try:
            login = await runtime.get_login_status()
        except RuntimeBackendError as exc:
            raise to_interface_error(exc) from exc
        record.updated_at = _now()
        self._save(record)
        return login

    async def search_posts(self, session_id: str, token: str, request: Any, view: str = "full") -> dict[str, Any]:
        record = self.verify_token(session_id, token)
        runtime = await self._runtime_for(record)
        await self._verified_login(runtime)
        payload = request.model_dump(exclude={"token"}, exclude_none=True)
        try:
            result = await runtime.search_posts(payload, view)
        except RuntimeBackendError as exc:
            raise to_interface_error(exc) from exc
        record.updated_at = _now()
        self._save(record)
        return result

    async def open_from_search(self, session_id: str, token: str, note_id: str, view: str = "full") -> dict[str, Any]:
        record = self.verify_token(session_id, token)
        runtime = await self._runtime_for(record)
        try:
            result = await runtime.open_note_from_search(note_id, view)
        except RuntimeBackendError as exc:
            raise to_interface_error(exc) from exc
        record.updated_at = _now()
        self._save(record)
        return result

    async def open_by_xsec(self, session_id: str, token: str, request: Any, view: str = "full") -> dict[str, Any]:
        record = self.verify_token(session_id, token)
        payload = request.model_dump(exclude={"token"}, exclude_none=True)
        runtime = await self._runtime_for(record)
        try:
            result = await runtime.open_note_by_xsec(payload, view)
        except RuntimeBackendError as exc:
            raise to_interface_error(exc) from exc
        record.updated_at = _now()
        self._save(record)
        return result

    async def root_comments(self, session_id: str, token: str, note_id: str, cursor: str | None, limit: int, view: str = "full") -> dict[str, Any]:
        record = self.verify_token(session_id, token)
        runtime = await self._runtime_for(record)
        try:
            result = await runtime.fetch_root_comments(note_id, cursor, limit, view)
        except RuntimeBackendError as exc:
            raise to_interface_error(exc) from exc
        record.updated_at = _now()
        self._save(record)
        return result

    async def sub_comments(self, session_id: str, token: str, root_comment_id: str, cursor: str | None, limit: int, view: str = "full") -> dict[str, Any]:
        record = self.verify_token(session_id, token)
        runtime = await self._runtime_for(record)
        try:
            result = await runtime.fetch_sub_comments(root_comment_id, cursor, limit, view)
        except RuntimeBackendError as exc:
            raise to_interface_error(exc) from exc
        record.updated_at = _now()
        self._save(record)
        return result

    @staticmethod
    def _runtime_payload(record: SessionRecord) -> dict[str, Any]:
        return {
            "session_id": record.session_id,
            "purpose": record.purpose,
            "user_data_dir": record.user_data_dir,
            "attach_settings": {},
        }

    async def _runtime_for(self, record: SessionRecord):
        if record.runtime is not None:
            return record.runtime
        self._ensure_user_data_dir(record)
        try:
            record.runtime = await self._runtime.create_session(self._runtime_payload(record))
        except RuntimeBackendError as exc:
            raise to_interface_error(exc, operation="create_session") from exc
        return record.runtime

    @staticmethod
    async def _verified_login(runtime) -> dict[str, Any]:
        try:
            login = await runtime.get_login_status()
        except RuntimeBackendError as exc:
            raise to_interface_error(exc) from exc
        if login.get("state") == "risk_blocked" or login.get("risk_triggered"):
            raise InterfaceError("risk_blocked", details={"login": login})
        if login.get("state") != "ready":
            raise InterfaceError("login_required")
        return login

    def _save(self, record: SessionRecord) -> None:
        self._persistence.save(record)

    @staticmethod
    def _ensure_user_data_dir(record: SessionRecord) -> None:
        Path(record.user_data_dir).mkdir(parents=True, exist_ok=True)
