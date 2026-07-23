from copy import deepcopy
from typing import Any, TypeAlias


Message: TypeAlias = dict[str, Any]
UserMessage: TypeAlias = str | list[Message]


def normalize_user_message(value: UserMessage) -> list[Message]:
    """Normalize one user input into the runtime's internal message list."""
    if isinstance(value, str):
        return [{"role": "user", "content": value}]

    if not isinstance(value, list):
        raise TypeError("current_user_message must be a string or list")
    if len(value) != 1:
        raise ValueError("current_user_message must contain exactly one message")

    message = value[0]
    if not isinstance(message, dict):
        raise TypeError("current user message must be a dict")
    if message.get("role") != "user":
        raise ValueError("current_user_message role must be 'user'")

    content = message.get("content")
    if not isinstance(content, (str, list)):
        raise TypeError(
            "current user message content must be a string or list"
        )

    return deepcopy(value)
