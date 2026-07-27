import json
from hashlib import sha256
from pathlib import Path

import pytest

from bumblehive_server.session_reader import SessionNotFoundError, SessionReader


@pytest.mark.asyncio
async def test_session_reader_lists_and_loads_json_sessions(tmp_path) -> None:
    reader = SessionReader(tmp_path)
    session_id = await reader.create("/tmp/demo")
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

    sessions = await reader.list()
    detail = await reader.get(session_id)

    assert sessions[0].title == "Hello"
    assert sessions[0].last_message == "Hi"
    assert sessions[0].workspace == str(Path("/tmp/demo").resolve())
    assert sessions[0].created_at <= sessions[0].updated_at
    assert detail.workspace == str(Path("/tmp/demo").resolve())
    assert detail.created_at == sessions[0].created_at
    assert detail.messages[-1]["content"] == "Hi"


@pytest.mark.asyncio
async def test_session_reader_prefers_persisted_display_title(tmp_path) -> None:
    reader = SessionReader(tmp_path)
    session_id = await reader.create_child(
        "/tmp/demo",
        title="  Inspect   concurrency  ",
        parent_session_id="parent-session",
    )
    path = tmp_path / f"{sha256(session_id.encode()).hexdigest()}.json"
    path.write_text(
        json.dumps(
            {
                "session_id": session_id,
                "messages": [
                    {
                        "role": "user",
                        "content": "A much longer self-contained task",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    sessions = await reader.list()

    assert sessions[0].title == "Inspect concurrency"
    metadata_path = (
        tmp_path
        / ".metadata"
        / f"{sha256(session_id.encode()).hexdigest()}.json"
    )
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["title"] == "Inspect concurrency"
    assert metadata["parent_session_id"] == "parent-session"


@pytest.mark.asyncio
async def test_session_reader_raises_for_missing_session(tmp_path) -> None:
    reader = SessionReader(tmp_path)
    with pytest.raises(SessionNotFoundError):
        await reader.get("missing")


@pytest.mark.asyncio
async def test_session_reader_creates_and_migrates_workspace_documents(
    tmp_path,
) -> None:
    reader = SessionReader(tmp_path)
    created_id = await reader.create(tmp_path / "created-workspace")

    created_path = tmp_path / f"{sha256(created_id.encode()).hexdigest()}.json"
    assert json.loads(created_path.read_text(encoding="utf-8")) == {
        "session_id": created_id,
        "messages": [],
    }
    created = await reader.get(created_id)
    assert created.workspace == str((tmp_path / "created-workspace").resolve())
    assert created.messages == []
    assert created.created_at <= created.updated_at

    legacy_id = "legacy-session"
    legacy_path = tmp_path / f"{sha256(legacy_id.encode()).hexdigest()}.json"
    legacy_path.write_text(
        json.dumps({"session_id": legacy_id, "messages": []}),
        encoding="utf-8",
    )
    original_document = legacy_path.read_text(encoding="utf-8")
    original_mtime = legacy_path.stat().st_mtime_ns

    migrated = await reader.migrate_missing_workspace(tmp_path / "legacy-workspace")

    assert migrated == 1
    assert (await reader.get(legacy_id)).workspace == str(
        (tmp_path / "legacy-workspace").resolve()
    )
    assert legacy_path.stat().st_mtime_ns == original_mtime
    assert legacy_path.read_text(encoding="utf-8") == original_document

    assert await reader.delete_metadata(legacy_id) is True
    assert await reader.delete_metadata(legacy_id) is False
