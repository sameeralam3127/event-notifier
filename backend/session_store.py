import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional


class SessionStore:
    def __init__(self, ttl_hours: int = 12):
        self._data: Dict[str, Dict[str, Any]] = {}
        self._expires_at: Dict[str, datetime] = {}
        self._ttl = timedelta(hours=ttl_hours)

    def _purge_expired(self):
        now = datetime.now(timezone.utc)
        for sid, expires_at in list(self._expires_at.items()):
            if expires_at <= now:
                self.remove(sid)

    def create_session(self) -> str:
        self._purge_expired()
        sid = str(uuid.uuid4())
        self._data[sid] = {}
        self._expires_at[sid] = datetime.now(timezone.utc) + self._ttl
        return sid

    def get(self, sid: str) -> Optional[Dict[str, Any]]:
        expires_at = self._expires_at.get(sid)
        if not expires_at or expires_at <= datetime.now(timezone.utc):
            self.remove(sid)
            return None
        self._expires_at[sid] = datetime.now(timezone.utc) + self._ttl
        return self._data.get(sid)

    def set(self, sid: str, key: str, value: Any):
        if sid in self._data:
            self._data[sid][key] = value

    def remove(self, sid: str):
        self._data.pop(sid, None)
        self._expires_at.pop(sid, None)


store = SessionStore()
