from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from bumblehive.tools import PathAllowlist


def test_path_allowlist_is_a_normalized_immutable_snapshot(tmp_path) -> None:
    root = tmp_path / "root"
    allowlist = PathAllowlist.from_roots(
        extra_read_roots=[root, root],
        extra_write_roots=[tmp_path / "write"],
    )

    assert allowlist.extra_read_roots == (root.resolve(),)
    assert allowlist.extra_write_roots == ((tmp_path / "write").resolve(),)
    with pytest.raises(FrozenInstanceError):
        allowlist.extra_read_roots = ()


@pytest.mark.parametrize(
    "factory",
    [
        lambda path: PathAllowlist.from_roots(extra_read_roots=path),
        lambda path: PathAllowlist(extra_read_roots=(str(path),)),
        lambda path: PathAllowlist(extra_write_roots=(Path("relative"),)),
    ],
)
def test_path_allowlist_rejects_ambiguous_or_unnormalized_inputs(tmp_path, factory) -> None:
    with pytest.raises((TypeError, ValueError)):
        factory(tmp_path)
