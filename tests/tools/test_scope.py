import pytest

from bumblehive.tools.scope import (
    bind_tool_workspace,
    current_tool_workspace,
    reset_tool_workspace,
)


def test_workspace_context_restores_nested_bindings_on_error(tmp_path):
    assert current_tool_workspace() is None
    outer = bind_tool_workspace(tmp_path / "outer")
    try:
        assert current_tool_workspace() == (tmp_path / "outer").resolve()
        with pytest.raises(RuntimeError, match="failed"):
            inner = bind_tool_workspace(tmp_path / "inner")
            try:
                assert current_tool_workspace() == (tmp_path / "inner").resolve()
                raise RuntimeError("failed")
            finally:
                reset_tool_workspace(inner)
        assert current_tool_workspace() == (tmp_path / "outer").resolve()
    finally:
        reset_tool_workspace(outer)
    assert current_tool_workspace() is None
