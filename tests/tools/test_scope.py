from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from bumblehive.tools import ToolPathPolicy


def test_path_policy_is_a_normalized_immutable_snapshot(tmp_path) -> None:
    root = tmp_path / "root"
    policy = ToolPathPolicy.from_roots(
        extra_read_roots=[root, root],
        extra_write_roots=[tmp_path / "write"],
    )

    assert policy.extra_read_roots == (root.resolve(),)
    assert policy.extra_write_roots == ((tmp_path / "write").resolve(),)
    assert policy.restrict_exec_paths is False
    with pytest.raises(FrozenInstanceError):
        policy.extra_read_roots = ()


@pytest.mark.parametrize(
    "factory",
    [
        lambda path: ToolPathPolicy.from_roots(extra_read_roots=path),
        lambda path: ToolPathPolicy(extra_read_roots=(str(path),)),
        lambda path: ToolPathPolicy(extra_write_roots=(Path("relative"),)),
        lambda path: ToolPathPolicy(restrict_exec_paths=path),
    ],
)
def test_path_policy_rejects_ambiguous_or_unnormalized_inputs(tmp_path, factory) -> None:
    with pytest.raises((TypeError, ValueError)):
        factory(tmp_path)
