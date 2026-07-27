import pytest

from bumblehive.observability import (
    TOOL_CALL_FINISHED,
    EventRecorder,
)
from bumblehive.observability.emitter import EventEmitter
from bumblehive.protocols import ToolCall
from bumblehive.tools import ToolManager


def _manager() -> ToolManager:
    manager = ToolManager()
    manager.register_builtin_tools()
    return manager


async def _execute(
    manager: ToolManager,
    workspace,
    name: str,
    arguments: dict,
):
    recorder = EventRecorder()
    result = await manager.execute_call(
        ToolCall(f"call-{name}", name, arguments),
        workspace=workspace,
        emitter=EventEmitter.from_hooks(recorder),
    )
    event = recorder.by_kind(TOOL_CALL_FINISHED)[0]
    return result, event


@pytest.mark.asyncio
async def test_edit_file_emits_real_unified_diff_without_changing_result(
    tmp_path,
) -> None:
    target = tmp_path / "plane_war.html"
    lines = [f"line {number}" for number in range(1, 151)]
    lines[119] = "const powerup = 'rapid';"
    target.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")

    result, event = await _execute(
        _manager(),
        tmp_path,
        "edit_file",
        {
            "path": "plane_war.html",
            "old_text": "const powerup = 'rapid';",
            "new_text": "const powerup = 'spread';",
        },
    )

    assert result.content["success"] is True
    assert not hasattr(result, "file_changes")
    assert event.payload["tool_result"]["name"] == "edit_file"
    assert event.payload["file_changes"] == [
        {
            "path": "plane_war.html",
            "added": 1,
            "deleted": 1,
            "unified_diff": (
                "--- plane_war.html\n"
                "+++ plane_war.html\n"
                "@@ -117,7 +117,7 @@\n"
                " line 117\n"
                " line 118\n"
                " line 119\n"
                "-const powerup = 'rapid';\n"
                "+const powerup = 'spread';\n"
                " line 121\n"
                " line 122\n"
                " line 123"
            ),
        }
    ]


@pytest.mark.asyncio
async def test_apply_patch_tracks_final_change_once_per_file(tmp_path) -> None:
    existing = tmp_path / "existing.txt"
    existing.write_text("first\nmiddle\nlast\n", encoding="utf-8")

    result, event = await _execute(
        _manager(),
        tmp_path,
        "apply_patch",
        {
            "edits": [
                {
                    "path": "existing.txt",
                    "action": "replace",
                    "old_text": "first",
                    "new_text": "updated-first",
                },
                {
                    "path": "existing.txt",
                    "action": "replace",
                    "old_text": "last",
                    "new_text": "updated-last",
                },
                {
                    "path": "created.txt",
                    "action": "add",
                    "new_text": "created\n",
                },
            ]
        },
    )

    assert result.content["success"] is True
    changes = event.payload["file_changes"]
    assert [change["path"] for change in changes] == [
        "existing.txt",
        "created.txt",
    ]
    assert changes[0]["added"] == 2
    assert changes[0]["deleted"] == 2
    assert changes[0]["unified_diff"].count("--- existing.txt") == 1
    assert changes[1]["added"] == 1
    assert changes[1]["deleted"] == 0
    assert "@@ -0,0 +1 @@" in changes[1]["unified_diff"]


@pytest.mark.asyncio
async def test_dry_run_failed_and_unchanged_calls_emit_no_file_changes(
    tmp_path,
) -> None:
    target = tmp_path / "notes.txt"
    target.write_text("same\n", encoding="utf-8")
    manager = _manager()

    dry_run, dry_run_event = await _execute(
        manager,
        tmp_path,
        "apply_patch",
        {
            "dry_run": True,
            "edits": [
                {
                    "path": "notes.txt",
                    "action": "replace",
                    "old_text": "same",
                    "new_text": "changed",
                }
            ],
        },
    )
    unchanged, unchanged_event = await _execute(
        manager,
        tmp_path,
        "write_file",
        {"path": "notes.txt", "content": "same\n"},
    )
    failed, failed_event = await _execute(
        manager,
        tmp_path,
        "edit_file",
        {
            "path": "notes.txt",
            "old_text": "missing",
            "new_text": "changed",
        },
    )

    assert dry_run.content["dry_run"] is True
    assert unchanged.content["success"] is True
    assert "old_text not found" in failed.content["error"]
    assert "file_changes" not in dry_run_event.payload
    assert "file_changes" not in unchanged_event.payload
    assert "file_changes" not in failed_event.payload


@pytest.mark.asyncio
async def test_large_diff_keeps_stats_without_emitting_malformed_diff(
    tmp_path,
) -> None:
    content = "\n".join(f"line {number}" for number in range(1, 1_101)) + "\n"

    result, event = await _execute(
        _manager(),
        tmp_path,
        "write_file",
        {"path": "large.txt", "content": content},
    )

    assert result.content["success"] is True
    assert event.payload["file_changes"] == [
        {
            "path": "large.txt",
            "added": 1_100,
            "deleted": 0,
            "truncated": True,
        }
    ]
