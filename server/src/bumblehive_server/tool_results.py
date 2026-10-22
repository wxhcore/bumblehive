"""Format background tool results delivered as conversation input."""

import json
from typing import Any


def format_background_tool_result(task_id: str, result: Any) -> str:
    content = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, default=str)
    return f"[Background tool result]\nTask ID: {task_id}\n\n{content}"
