from copy import deepcopy

import pytest

from bumblehive.protocols import normalize_user_message


def test_normalize_user_message_wraps_text_and_clones_messages() -> None:
    assert normalize_user_message("hello") == [
        {"role": "user", "content": "hello"}
    ]

    current_messages = [
        {
            "role": "user",
            "content": [{"type": "text", "text": "inspect"}],
        }
    ]
    original = deepcopy(current_messages)

    normalized = normalize_user_message(current_messages)
    normalized[0]["content"].append({"type": "text", "text": "changed"})

    assert current_messages == original


@pytest.mark.parametrize(
    ("value", "error", "match"),
    [
        ([], ValueError, "exactly one"),
        (
            {"role": "user", "content": "bare dict"},
            TypeError,
            "string or list",
        ),
        (
            [
                {"role": "user", "content": "one"},
                {"role": "user", "content": "two"},
            ],
            ValueError,
            "exactly one",
        ),
        ([{"role": "assistant", "content": "no"}], ValueError, "role must"),
        ([{"role": "user", "content": None}], TypeError, "string or list"),
        ([123], TypeError, "must be a dict"),
    ],
)
def test_normalize_user_message_rejects_invalid_inputs(
    value,
    error,
    match,
) -> None:
    with pytest.raises(error, match=match):
        normalize_user_message(value)
