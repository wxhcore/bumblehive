import bumblehive
import bumblehive.agent
import bumblehive.config
import bumblehive.observability
import bumblehive.protocols
import bumblehive.providers
import bumblehive.session
import bumblehive.session.stores
import bumblehive.skills
import bumblehive.tools
import bumblehive.tools.adapters
import bumblehive.tools.builtins
import bumblehive.tools.mcp

from tests.public_api_contract import PUBLIC_API


def test_public_api_contract() -> None:
    for module, expected in PUBLIC_API.items():
        assert set(module.__all__) == expected
        assert all(hasattr(module, name) for name in expected)


NON_PUBLIC_REEXPORTS = {
    bumblehive: {
        "AgentConfig",
        "AsyncEventStream",
        "AsyncEventStreamHook",
        "EventEmitter",
        "ProviderConfig",
        "ProviderManager",
        "RuntimeConfig",
        "get_sessions_path",
        "get_workspace_path",
    },
    bumblehive.agent: {
        "AgentEvent",
        "AgentHook",
        "CheckpointCallback",
        "ContextGovernanceConfig",
        "ContextGovernor",
        "EventEmitter",
        "EventRecorder",
        "prepare_history",
        "repair_message_sequence",
    },
    bumblehive.observability: {
        "AsyncEventStreamHook",
        "CompositeHook",
        "EventEmitter",
        "ModelEvents",
        "RunEvents",
        "ToolEvents",
        "TurnEvents",
        "error_payload",
        "make_event",
        "new_run_id",
        "normalize_hooks",
    },
    bumblehive.providers: {
        "resolve_stream_idle_timeout_s",
    },
    bumblehive.session: {
        "SessionManager",
        "SessionState",
    },
    bumblehive.tools: {
        "MCPManager",
        "MCPToolWrapper",
        "ToolExecutor",
        "register_builtin_tools",
    },
}


def test_internal_types_are_not_reexported() -> None:
    for module, internal_names in NON_PUBLIC_REEXPORTS.items():
        assert all(not hasattr(module, name) for name in internal_names)
