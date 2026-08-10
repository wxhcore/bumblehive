from pathlib import Path

import pytest

from bumblehive.protocols import ToolCall
from bumblehive.tools import ToolPathPolicy, ToolManager


def _manager():
    manager = ToolManager()
    manager.register_builtin_tools()
    return manager


async def _patch(manager, workspace, edits, *, dry_run=False, policy=ToolPathPolicy()):
    return await manager.execute_call(
        ToolCall("patch", "apply_patch", {"edits": edits, "dry_run": dry_run}),
        workspace=workspace,
        path_policy=policy,
    )


@pytest.mark.asyncio
async def test_apply_patch_previews_then_commits_a_multi_file_change(tmp_path) -> None:
    existing = tmp_path / "existing.txt"
    existing.write_text("hello\n", encoding="utf-8")
    edits = [
        {
            "path": "existing.txt",
            "action": "replace",
            "old_text": "hello",
            "new_text": "updated",
        },
        {"path": "created.txt", "action": "add", "new_text": "created\n"},
        {"path": "created.txt", "action": "add", "new_text": "again\n"},
    ]
    manager = _manager()

    preview = await _patch(manager, tmp_path, edits, dry_run=True)
    assert preview.content["success"] is True
    assert preview.content["dry_run"] is True
    assert existing.read_text(encoding="utf-8") == "hello\n"
    assert not (tmp_path / "created.txt").exists()

    committed = await _patch(manager, tmp_path, edits)
    assert committed.content["success"] is True
    assert committed.content["dry_run"] is False
    assert existing.read_text(encoding="utf-8") == "updated\n"
    assert (tmp_path / "created.txt").read_text(encoding="utf-8") == "created\nagain\n"


@pytest.mark.asyncio
async def test_apply_patch_accepts_absolute_paths_only_in_write_roots(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    write_root = tmp_path / "write"
    outside = tmp_path / "outside"
    workspace.mkdir()
    write_root.mkdir()
    outside.mkdir()
    manager = _manager()
    policy = ToolPathPolicy.from_roots(extra_write_roots=[write_root])

    allowed = await _patch(
        manager,
        workspace,
        [{"path": str(write_root / "created.txt"), "action": "add", "new_text": "yes"}],
        policy=policy,
    )
    blocked = await _patch(
        manager,
        workspace,
        [{"path": str(outside / "blocked.txt"), "action": "add", "new_text": "no"}],
        policy=policy,
    )

    assert allowed.content["success"] is True
    assert (write_root / "created.txt").read_text(encoding="utf-8") == "yes\n"
    assert "outside writable roots" in blocked.content["error"]
    assert not (outside / "blocked.txt").exists()


@pytest.mark.asyncio
async def test_apply_patch_validates_schema_and_replace_uniqueness(tmp_path) -> None:
    (tmp_path / "notes.txt").write_text("same\nsame\n", encoding="utf-8")
    manager = _manager()

    missing_text = await manager.execute_call(
        ToolCall(
            "invalid",
            "apply_patch",
            {"edits": [{"path": "notes.txt", "action": "replace", "new_text": "new"}]},
        ),
        workspace=tmp_path,
    )
    ambiguous = await _patch(
        manager,
        tmp_path,
        [{"path": "notes.txt", "action": "replace", "old_text": "same", "new_text": "new"}],
    )

    assert missing_text.error is not None
    assert missing_text.error.code == "invalid_tool_arguments"
    assert "appears multiple times" in ambiguous.content["error"]
    assert (tmp_path / "notes.txt").read_text(encoding="utf-8") == "same\nsame\n"


@pytest.mark.asyncio
async def test_apply_patch_rolls_back_every_file_when_a_write_fails(
    tmp_path,
    monkeypatch,
) -> None:
    existing = tmp_path / "existing.txt"
    created = tmp_path / "created.txt"
    failing = tmp_path / "failing.txt"
    existing.write_text("original\n", encoding="utf-8")
    original_write_text = Path.write_text
    failed = False

    def fail_created_file_once(path, data, *args, **kwargs):
        nonlocal failed
        if path == failing and not failed:
            failed = True
            raise OSError("simulated write failure")
        return original_write_text(path, data, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", fail_created_file_once)

    result = await _patch(
        _manager(),
        tmp_path,
        [
            {
                "path": "existing.txt",
                "action": "replace",
                "old_text": "original",
                "new_text": "changed",
            },
            {"path": "created.txt", "action": "add", "new_text": "new"},
            {"path": "failing.txt", "action": "add", "new_text": "fail"},
        ],
    )

    assert result.content == {"error": "simulated write failure"}
    assert existing.read_text(encoding="utf-8") == "original\n"
    assert not created.exists()
    assert not failing.exists()
