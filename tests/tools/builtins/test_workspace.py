import pytest

from bumblehive.protocols import ToolCall
from bumblehive.tools import ToolManager
from bumblehive.tools.builtins.workspace import FileStateStore
from bumblehive.tools.scope import bind_tool_session, reset_tool_session


def test_file_state_store_is_a_bounded_lru() -> None:
    store = FileStateStore(max_entries=2)
    state_a = store.for_session("a")
    state_b = store.for_session("b")
    assert store.for_session("a") is state_a

    store.for_session("c")

    assert len(store) == 2
    assert store.for_session("b") is not state_b
    with pytest.raises(ValueError, match="positive"):
        FileStateStore(max_entries=0)


async def _execute(manager, workspace, session_id, name, arguments):
    token = bind_tool_session(session_id)
    try:
        return await manager.execute_call(
            ToolCall(f"{session_id}-{name}", name, arguments),
            workspace=workspace,
        )
    finally:
        reset_tool_session(token)


@pytest.mark.asyncio
async def test_file_read_and_edit_state_is_isolated_by_session(tmp_path) -> None:
    (tmp_path / "dedup.txt").write_text("same\n", encoding="utf-8")
    (tmp_path / "edit.txt").write_text("hello\n", encoding="utf-8")
    manager = ToolManager()
    manager.register_builtin_tools()

    first_a = await _execute(manager, tmp_path, "a", "read_file", {"path": "dedup.txt"})
    first_b = await _execute(manager, tmp_path, "b", "read_file", {"path": "dedup.txt"})
    second_a = await _execute(manager, tmp_path, "a", "read_file", {"path": "dedup.txt"})
    await _execute(manager, tmp_path, "a", "read_file", {"path": "edit.txt"})
    edit_b = await _execute(
        manager,
        tmp_path,
        "b",
        "edit_file",
        {"path": "edit.txt", "old_text": "hello", "new_text": "hi"},
    )

    assert first_a.content["deduplicated"] is False
    assert first_b.content["deduplicated"] is False
    assert second_a.content["deduplicated"] is True
    assert "not been read" in edit_b.content["warning"]
