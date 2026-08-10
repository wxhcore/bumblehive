import os

import pytest

from bumblehive.protocols import ToolCall
from bumblehive.tools import ToolPathPolicy, ToolManager


def _manager():
    manager = ToolManager()
    manager.register_builtin_tools()
    return manager


async def _execute(manager, workspace, name, arguments, *, policy=ToolPathPolicy()):
    return await manager.execute_call(
        ToolCall(f"call-{name}", name, arguments),
        workspace=workspace,
        path_policy=policy,
    )


@pytest.mark.asyncio
async def test_find_files_filters_sorts_and_paginates_project_paths(tmp_path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "alpha.py").write_text("", encoding="utf-8")
    (tmp_path / "src" / "beta.py").write_text("", encoding="utf-8")
    (tmp_path / "src" / "notes.md").write_text("", encoding="utf-8")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "hidden.py").write_text("", encoding="utf-8")
    manager = _manager()

    first = await _execute(
        manager,
        tmp_path,
        "find_files",
        {"path": ".", "query": "src", "type": "py", "head_limit": 1},
    )
    second = await _execute(
        manager,
        tmp_path,
        "find_files",
        {"path": ".", "query": "src", "glob": "*.py", "head_limit": 1, "offset": 1},
    )

    assert first.content == {
        "matches": ["src/alpha.py"],
        "total_matches": 2,
        "offset": 0,
        "truncated": True,
    }
    assert second.content["matches"] == ["src/beta.py"]
    assert ".git/hidden.py" not in str(first.content)


@pytest.mark.asyncio
async def test_grep_supports_file_count_and_content_modes(tmp_path) -> None:
    old = tmp_path / "old.txt"
    new = tmp_path / "new.txt"
    old.write_text("before\nneedle old\nafter\n", encoding="utf-8")
    new.write_text("needle new\nneedle again\n", encoding="utf-8")
    os.utime(old, (100, 100))
    os.utime(new, (200, 200))
    manager = _manager()

    files = await _execute(
        manager,
        tmp_path,
        "grep",
        {"pattern": "needle", "output_mode": "files_with_matches"},
    )
    counts = await _execute(
        manager,
        tmp_path,
        "grep",
        {"pattern": "needle", "output_mode": "count"},
    )
    content = await _execute(
        manager,
        tmp_path,
        "grep",
        {
            "pattern": "NEEDLE OLD",
            "case_insensitive": True,
            "output_mode": "content",
            "context_before": 1,
            "context_after": 1,
        },
    )

    assert files.content["files"] == ["new.txt", "old.txt"]
    assert counts.content["counts"] == [
        {"path": "new.txt", "count": 2},
        {"path": "old.txt", "count": 1},
    ]
    assert content.content["total_matches"] == 1
    assert content.content["matches"][0]["path"] == "old.txt"
    assert "before" in str(content.content["matches"][0])


@pytest.mark.asyncio
async def test_search_reads_policyed_roots_but_not_escaping_symlinks(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    read_root = tmp_path / "skills"
    outside = tmp_path / "outside"
    workspace.mkdir()
    read_root.mkdir()
    outside.mkdir()
    (read_root / "SKILL.md").write_text("find needle\n", encoding="utf-8")
    secret = outside / "secret.txt"
    secret.write_text("outside-secret\n", encoding="utf-8")
    link = read_root / "linked-secret.txt"
    try:
        link.symlink_to(secret)
    except OSError as exc:
        pytest.skip(f"symlinks are not supported: {exc}")
    policy = ToolPathPolicy.from_roots(extra_read_roots=[read_root])
    manager = _manager()

    grep = await _execute(
        manager,
        workspace,
        "grep",
        {"pattern": "needle|outside-secret", "path": str(read_root)},
        policy=policy,
    )
    found = await _execute(
        manager,
        workspace,
        "find_files",
        {"path": str(read_root)},
        policy=policy,
    )

    assert grep.content["files"] == ["SKILL.md"]
    assert grep.content["skipped_unreadable"] == 1
    assert found.content["matches"] == ["SKILL.md"]


@pytest.mark.asyncio
async def test_grep_reports_binary_and_large_files_as_skipped(tmp_path) -> None:
    (tmp_path / "ok.txt").write_text("needle\n", encoding="utf-8")
    (tmp_path / "binary.bin").write_bytes(b"\x00needle\n")
    (tmp_path / "large.txt").write_text("needle\n" + "x" * 2_000_000, encoding="utf-8")

    result = await _execute(
        _manager(),
        tmp_path,
        "grep",
        {"pattern": "needle", "output_mode": "files_with_matches"},
    )

    assert result.content["files"] == ["ok.txt"]
    assert result.content["skipped_binary"] == 1
    assert result.content["skipped_large"] == 1
