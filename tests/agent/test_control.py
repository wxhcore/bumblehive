import pytest

from bumblehive.agent.control import _RunControl


def test_queue_copies_input_and_drains_ordered_snapshots() -> None:
    control = _RunControl()
    message = [{"role": "user", "content": [{"type": "text", "text": "second"}]}]
    control.steer("first")
    control.steer(message)
    message[0]["content"][0]["text"] = "mutated"
    assert not control._close_if_empty()
    with pytest.raises(RuntimeError):
        control.take_pending()
    snapshot = control._drain_all()
    control.steer("third")
    assert snapshot == [
        {"role": "user", "content": "first"},
        {"role": "user", "content": [{"type": "text", "text": "second"}]},
    ]
    control._close()
    control._close()
    assert control.take_pending() == [{"role": "user", "content": "third"}]
    assert control.take_pending() == []
    with pytest.raises(RuntimeError):
        control.steer("late")


def test_empty_check_closes_input() -> None:
    control = _RunControl()
    assert control._close_if_empty()
    with pytest.raises(RuntimeError):
        control.steer("too late")


@pytest.mark.parametrize(
    "message",
    [
        None,
        {},
        [],
        [{"role": "assistant", "content": "x"}],
        [{"role": "user", "content": 3}],
        ["x"],
    ],
)
def test_invalid_input_does_not_modify_queue(message) -> None:
    control = _RunControl()
    control.steer("valid")
    with pytest.raises((TypeError, ValueError)):
        control.steer(message)
    assert control._drain_all() == [{"role": "user", "content": "valid"}]
