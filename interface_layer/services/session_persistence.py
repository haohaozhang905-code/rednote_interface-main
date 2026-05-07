from __future__ import annotations

import json
import shutil
from pathlib import Path

from .session_record import SessionRecord


class SessionPersistence:
    def __init__(self, profile_root: Path) -> None:
        self.profile_root = Path(profile_root)

    def load(self) -> list[SessionRecord]:
        records: list[SessionRecord] = []
        for path in sorted(self.profile_root.glob("sess_*/session.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                payload["user_data_dir"] = str(path.parent / "profile")
                records.append(SessionRecord.from_persistent(payload))
            except (OSError, KeyError, TypeError, json.JSONDecodeError):
                continue
        return records

    def save(self, record: SessionRecord) -> None:
        session_dir = self.profile_root / record.session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        target = session_dir / "session.json"
        temp = session_dir / "session.json.tmp"
        temp.write_text(
            json.dumps(record.persistent_state(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temp.replace(target)

    def delete(self, session_id: str) -> None:
        root = self.profile_root.resolve()
        target = (root / session_id).resolve()
        if target == root or root not in target.parents:
            return
        if target.exists():
            shutil.rmtree(target)
