import asyncio
import threading

import pytest

from bumblehive.session import SessionManager


def _assistant_call(call_id: str) -> dict:
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": call_id,
                "type": "function",
                "function": {"name": "read_file", "arguments": "{}"},
            }
        ],
    }


@pytest.mark.asyncio
async def test_manager_caches_checkpoints_and_reloads_persisted_history(tmp_path) -> None:
    manager = SessionManager(tmp_path)
    first, second = await asyncio.gather(manager.get("demo"), manager.get("demo"))
    assert first is second

    await manager.append_user(first, "question")
    checkpoint = manager.create_checkpoint_callback(first)
    await checkpoint(
        [
            {"role": "system", "content": "runtime"},
            {
                "role": "user",
                "content": "question\n\n<runtime_context>\nold\n</runtime_context>",
            },
            {"role": "assistant", "content": "answer"},
        ]
    )

    assert manager.get_history(first) == [
        {"role": "user", "content": "question"},
        {"role": "assistant", "content": "answer"},
    ]
    reloaded = await SessionManager(tmp_path).get("demo")
    assert reloaded.history.get_history() == manager.get_history(first)

    await manager.clear("demo")
    assert manager.get_history(first) == []
    assert await manager.delete("demo") is True
    assert await manager.delete("demo") is False


@pytest.mark.asyncio
async def test_manager_appends_message_list_without_nesting_or_mutation(
    tmp_path,
) -> None:
    manager = SessionManager(tmp_path)
    session = await manager.get("message-list")
    current_messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "inspect this"},
            ],
        }
    ]

    await manager.append_user(session, current_messages)
    current_messages[0]["content"].append(
        {"type": "text", "text": "changed later"}
    )

    expected = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "inspect this"},
            ],
        }
    ]
    assert manager.get_history(session) == expected
    reloaded = await SessionManager(tmp_path).get("message-list")
    assert reloaded.history.get_history() == expected


@pytest.mark.asyncio
async def test_manager_rejects_invalid_input_without_mutating_session(
    tmp_path,
) -> None:
    manager = SessionManager(tmp_path)
    session = await manager.get("invalid-input")
    await manager.append_user(session, "existing")

    with pytest.raises(ValueError, match="role must"):
        await manager.append_user(
            session,
            [{"role": "assistant", "content": "invalid"}],
        )

    assert manager.get_history(session) == [
        {"role": "user", "content": "existing"}
    ]
    reloaded = await SessionManager(tmp_path).get("invalid-input")
    assert reloaded.history.get_history() == manager.get_history(session)


@pytest.mark.asyncio
async def test_manager_recovers_interrupted_user_and_tool_boundaries(tmp_path) -> None:
    manager = SessionManager(tmp_path)
    user_session = await manager.get("user-interrupted")
    await manager.append_user(user_session, "unfinished")

    assert await manager.recover(user_session) is True
    assert manager.get_history(user_session)[-1]["role"] == "assistant"
    assert "interrupted" in manager.get_history(user_session)[-1]["content"].lower()
    assert await manager.recover(user_session) is False

    tool_session = await manager.get("tool-interrupted")
    await manager.replace_and_save(
        tool_session,
        [{"role": "user", "content": "run"}, _assistant_call("missing")],
    )

    assert await manager.recover(tool_session) is True
    recovered = manager.get_history(tool_session)
    assert [message["role"] for message in recovered[-2:]] == ["tool", "assistant"]
    assert recovered[-2]["tool_call_id"] == "missing"
    assert "after tool execution" in recovered[-1]["content"].lower()


@pytest.mark.asyncio
async def test_manager_finishes_cancelled_save_before_publishing_the_same_snapshot(
    tmp_path,
    monkeypatch,
) -> None:
    manager = SessionManager(tmp_path)
    session = await manager.get("cancelled-save")
    await manager.replace_and_save(
        session,
        [{"role": "user", "content": "before"}],
    )

    save_started = threading.Event()
    release_save = threading.Event()
    original_save = manager._store._save

    def blocking_save(session_id, messages) -> None:
        save_started.set()
        release_save.wait(timeout=2)
        original_save(session_id, messages)

    monkeypatch.setattr(manager._store, "_save", blocking_save)
    expected = [
        {"role": "user", "content": "before"},
        {"role": "assistant", "content": "after"},
    ]
    task = asyncio.create_task(manager.replace_and_save(session, expected))
    assert await asyncio.to_thread(save_started.wait, 1)

    task.cancel()
    release_save.set()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert manager.get_history(session) == expected
    reloaded = await SessionManager(tmp_path).get("cancelled-save")
    assert reloaded.history.get_history() == expected
    assert not list(tmp_path.glob("*.tmp"))


@pytest.mark.parametrize("session_id", ["", "   ", None, 123])
@pytest.mark.asyncio
async def test_manager_rejects_invalid_session_ids(tmp_path, session_id) -> None:
    manager = SessionManager(tmp_path)
    with pytest.raises((TypeError, ValueError)):
        await manager.get(session_id)
