from .models import SessionState


DEFAULT_SESSION_ID = "default"


class SessionManager:
    """Manage in-memory conversation sessions for one runtime."""

    def __init__(self, *, default_session_id: str = DEFAULT_SESSION_ID) -> None:
        self.default_session_id = _normalize_session_id(default_session_id)
        self._sessions: dict[str, SessionState] = {}

    def get(self, session_id: str | None = None) -> SessionState:
        """Return the session state for ``session_id``, creating it if needed."""
        resolved = self.resolve_session_id(session_id)
        session = self._sessions.get(resolved)
        if session is None:
            session = SessionState(session_id=resolved)
            self._sessions[resolved] = session
        return session

    def resolve_session_id(self, session_id: str | None = None) -> str:
        """Return a validated session id, defaulting when omitted."""
        if session_id is None:
            return self.default_session_id
        return _normalize_session_id(session_id)


def _normalize_session_id(session_id: str) -> str:
    if not isinstance(session_id, str):
        raise TypeError("session_id must be a string")
    if not session_id.strip():
        raise ValueError("session_id must not be empty")
    return session_id
