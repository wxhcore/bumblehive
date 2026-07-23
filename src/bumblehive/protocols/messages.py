from typing import Any, TypeAlias


Message: TypeAlias = dict[str, Any]
UserMessage: TypeAlias = str | list[Message]
