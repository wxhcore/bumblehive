"""Register the desktop ask_user tool and route calls to their session."""

from collections.abc import Callable

from bumblehive import BumblehiveRuntime
from bumblehive.tools.scope import current_tool_session_id

from .session import SessionController


def register_ask_user_tool(
    runtime: BumblehiveRuntime,
    controller_for: Callable[[str], SessionController | None],
) -> None:
    @runtime.tools.tool(
        name="ask_user",
        description=(
            "Ask the user when information needed for the task cannot be determined from "
            "the available context.\n\n"
            "Waits up to 60 seconds, then returns pending and waits in the background for "
            "up to 120 more seconds before automatically skipping. Results share a task_id "
            "matching this tool call ID.\n"
            "- answered: Use the user's answer to continue.\n"
            "- pending: The question remains open; its final result will arrive automatically. "
            "Continue independent work without polling or repeating the question. If all "
            "remaining work depends on the answer, explain the blocker and end the current turn.\n"
            "- skipped: The question ended without an answer, through a skip or timeout. "
            "Do not repeat it.\n"
            "Neither pending nor skipped grants approval or selects a recommended option."
        ),
        parameters={
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "minLength": 1,
                    "description": (
                        "One concise, self-contained question about information needed "
                        "for the task. Use terms the user understands."
                    ),
                },
                "options": {
                    "type": "array",
                    "items": {"type": "string", "minLength": 1},
                    "description": (
                        "Optional suggested answers. Put a recommended option first when "
                        "appropriate and briefly explain its tradeoff in the same string. "
                        "Omit or pass an empty list for free-text input only. Do not add an "
                        "'Other' option; free-text input is always available."
                    ),
                },
            },
            "required": ["question"],
            "additionalProperties": False,
        },
    )
    async def ask_user(question: str, options: list[str] | None = None) -> dict:
        session_id = current_tool_session_id()
        controller = controller_for(session_id) if session_id else None
        if controller is None:
            raise RuntimeError("ask_user requires an active server conversation")
        return await controller.ask_user(question, options or [])
