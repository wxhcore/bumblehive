import json

import pytest

from bumblehive.session.stores.json_file import JsonSessionStore, SessionFileError


@pytest.mark.asyncio
async def test_store_creates_directory_only_when_a_session_is_saved(tmp_path) -> None:
    directory = tmp_path / "sessions"
    store = JsonSessionStore(directory)

    assert store.directory == directory.resolve()
    assert not directory.exists()

    assert await store.load("missing") is None
    assert await store.delete("missing") is False
    assert not directory.exists()

    await store.save("created", [])

    assert directory.is_dir()


@pytest.mark.asyncio
async def test_store_persists_loads_and_deletes_one_session(tmp_path) -> None:
    store = JsonSessionStore(tmp_path)
    messages = [{"role": "user", "content": "你好"}]

    await store.save("session/a", messages)

    files = list(tmp_path.glob("*.json"))
    assert len(files) == 1
    assert files[0].name != "session/a.json"
    assert await store.load("session/a") == messages
    assert await store.load("missing") is None
    assert await store.delete("session/a") is True
    assert await store.delete("session/a") is False


@pytest.mark.asyncio
async def test_store_reports_corrupt_and_unserializable_documents(tmp_path) -> None:
    store = JsonSessionStore(tmp_path)
    await store.save("corrupt", [])
    corrupt_path = next(tmp_path.glob("*.json"))
    corrupt_path.write_text(
        json.dumps({"session_id": "other", "messages": []}),
        encoding="utf-8",
    )

    with pytest.raises(SessionFileError, match="Failed to load session"):
        await store.load("corrupt")
    with pytest.raises(SessionFileError, match="Failed to save session"):
        await store.save("bad", [{"role": "user", "content": object()}])

    assert not [path for path in tmp_path.iterdir() if path.suffix == ".tmp"]
