"""Per-run desktop agent instructions and tool selection."""

from typing import Any, Literal

from bumblehive import BumblehiveRuntime
from bumblehive.agent.context.builder import load_prompt

AgentRole = Literal["single", "router", "worker"]
_ROUTER_TOOLS = {"read_file", "list_dir", "find_files", "grep", "ask_user", "sub_agent", "send_message"}
_EXCLUDED_TOOLS = {"single": {"sub_agent", "send_message"}, "worker": {"sub_agent", "ask_user"}}
_ROLE_INSTRUCTIONS = {
    "router": (
        "Answer directly when you can fulfill the request with the context and tools available. "
        "When delegating, give each worker a clear objective, the context it needs, and the expected "
        "deliverable. Keep parallel assignments independent. If all remaining work depends on a "
        "pending result, end the turn and wait for delivery. Use the results to fulfill the user's "
        "original request in the requested form."
    ),
    "worker": (
        "Complete the assigned task and return the requested deliverable in the requested form. "
        "If something prevents completion, say what remains open and why. "
        "Your final report is delivered automatically to the parent."
    ),
}


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
    if role == "router":
        allowed.intersection_update(_ROUTER_TOOLS)
    else:
        allowed.difference_update(_EXCLUDED_TOOLS[role])
    instructions = _ROLE_INSTRUCTIONS.get(role)
    if role == "worker" and not delegated:
        # An idle worker chat reopened by the user has no active parent task to message.
        allowed.discard("send_message")
        instructions = "Respond directly to the user in this worker conversation using your available tools."
    selection = requested if requested is not None else configured
    if selection is None:
        selection = registered
    agent["tool_names"] = [name for name in selection if name in allowed]
    if role == "worker" and delegated and "send_message" in agent["tool_names"]:
        instructions += (
            " Use send_message(target='parent', message=...) when a finding changes the parent's "
            "next step or you need a decision. Continue any work that can proceed independently."
        )
    if instructions:
        base = agent.get("instructions", runtime.config.agent.instructions) or load_prompt("agent_instructions.md")
        agent["instructions"] = base + "\n\n" + instructions
    return {**config, "agent": agent}
