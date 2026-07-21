import json
from hashlib import sha256

import pytest

from bumblehive_server.session_reader import SessionNotFoundError, SessionReader


@pytest.mark.asyncio
async def test_session_reader_lists_and_loads_json_sessions(tmp_path) -> None:
    session_id = "session-1"
    path = tmp_path / f"{sha256(session_id.encode()).hexdigest()}.json"
    path.write_text(
        json.dumps(
            {
                "session_id": session_id,
                "messages": [
                    {"role": "user", "content": "Hello"},
                    {"role": "assistant", "content": "Hi"},
                ],
            }
        ),
        encoding="utf-8",
    )

    reader = SessionReader(tmp_path)
    sessions = await reader.list()
    detail = await reader.get(session_id)

    assert sessions[0].title == "Hello"
    assert sessions[0].last_message == "Hi"
    assert detail.messages[-1]["content"] == "Hi"


@pytest.mark.asyncio
async def test_session_reader_raises_for_missing_session(tmp_path) -> None:
    reader = SessionReader(tmp_path)
    with pytest.raises(SessionNotFoundError):
        await reader.get("missing")

