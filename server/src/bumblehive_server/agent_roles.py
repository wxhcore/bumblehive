"""Per-run desktop agent instructions and tool selection."""

from typing import Any, Literal

from bumblehive import BumblehiveRuntime
from bumblehive.agent.context.builder import load_prompt

AgentRole = Literal["single", "router", "worker"]
_ROUTER_TOOLS = {"read_file", "list_dir", "find_files", "grep", "ask_user", "sub_agent", "send_message"}
_EXCLUDED_TOOLS = {"single": {"sub_agent", "send_message"}, "worker": {"sub_agent", "ask_user"}}
_ROLE_INSTRUCTIONS = {
    "router": (
        "You and your workers act as one assistant. Use your own tools or delegate to a worker "
        "to fulfill the user's request. When deciding whether you can complete an action, "
        "consider the tools available to both you and your workers. "
        "When delegating, give each worker a clear objective, the context it needs, and the expected "
        "deliverable. Keep parallel assignments independent. "
        "Worker reports arrive automatically as conversation input and may start a new turn. "
        "Match each report to the current assignment using its task ID. Progress updates and "
        "delivery receipts leave the assignment open. "
        "When some results are in and required assignments are still pending, acknowledge in one "
        "sentence what is done and what remains. Continue any work that can proceed, ask the user "
        "if a decision is needed, or end the turn if all that remains is to wait. "
        "Once all required assignments have reported an outcome, finish any remaining integration "
        "or verification and answer the original request in the requested form. Mention failures "
        "or verification limits that affect the result."
    ),
    "worker": (
        "Complete the assigned task and return the requested deliverable in the requested form. "
        "If something prevents completion, say what remains open and why. "
        "Your final report is delivered automatically to the parent."
    ),
}


def _role_tool_names(enabled: list[str], role: AgentRole, *, delegated: bool = False) -> list[str]:
    if role == "router":
        return [name for name in enabled if name in _ROUTER_TOOLS]
    excluded = _EXCLUDED_TOOLS[role]
    if role == "worker" and not delegated:
        # An idle worker chat reopened by the user has no active parent task to message.
        excluded = excluded | {"send_message"}
    return [name for name in enabled if name not in excluded]


def role_config(
    runtime: BumblehiveRuntime, config: dict | None, role: AgentRole, *, delegated: bool = False,
) -> dict[str, Any]:
    config = config or {}
    agent = dict(config.get("agent") or {})
    configured = runtime.config.agent.tool_names
    requested = agent.get("tool_names")
    if requested is not None and (
        not isinstance(requested, (list, tuple)) or not all(isinstance(name, str) for name in requested)
    ):
        raise ValueError("agent.tool_names must be a list of tool names")
    registered = runtime.tools.tool_names
    allowed = set(registered)
    if configured is not None:
        allowed.intersection_update(configured)
    selection = requested if requested is not None else configured
    if selection is None:
        selection = registered
    enabled = [name for name in selection if name in allowed]
    agent["tool_names"] = _role_tool_names(enabled, role, delegated=delegated)
    instructions = _ROLE_INSTRUCTIONS.get(role)
    if role == "router":
        worker_tools = _role_tool_names(enabled, "worker", delegated=True)
        instructions += "\n\nTools available to a delegated worker this turn: " + (", ".join(worker_tools) or "none")
    elif role == "worker" and not delegated:
        instructions = "Respond directly to the user in this worker conversation using your available tools."
    elif role == "worker" and "send_message" in agent["tool_names"]:
        instructions += (
            " Use send_message(target='parent', message=...) when a finding changes the parent's "
            "next step or you need a decision. Continue any work that can proceed independently."
        )
    if instructions:
        base = agent.get("instructions", runtime.config.agent.instructions) or load_prompt("agent_instructions.md")
        agent["instructions"] = base + "\n\n" + instructions
    return {**config, "agent": agent}
