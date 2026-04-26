import uuid
from typing import Any, Dict, Optional


class SessionStore:
    def __init__(self):
        self._data: Dict[str, Dict[str, Any]] = {}

    def create_session(self) -> str:
        sid = str(uuid.uuid4())
        self._data[sid] = {}
        return sid

    def get(self, sid: str) -> Optional[Dict[str, Any]]:
        return self._data.get(sid)

    def set(self, sid: str, key: str, value: Any):
        if sid in self._data:
            self._data[sid][key] = value

    def remove(self, sid: str):
        self._data.pop(sid, None)


store = SessionStore()
