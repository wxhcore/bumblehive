"""Canonical public Python API contract shared by tests and docs checks."""

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


PUBLIC_API = {
    bumblehive: {
        "AgentEvent",
        "AgentHook",
        "AgentLoop",
        "AgentRunResult",
        "BumblehiveConfig",
        "BumblehiveRuntime",
        "EventRecorder",
        "MessageHistory",
        "RuntimeArguments",
        "SkillsManager",
        "ToolCallingRunner",
        "ToolManager",
        "from_config",
    },
    bumblehive.agent: {
        "AgentLoop",
        "AgentRunResult",
        "ContextBuilder",
        "MessageHistory",
        "ToolCallingRunner",
    },
    bumblehive.config: {
        "AgentConfig",
        "BumblehiveConfig",
        "ConfigInput",
        "ProviderConfig",
        "RuntimeArguments",
        "RuntimeConfig",
        "load_config",
        "load_json_config",
    },
    bumblehive.observability: {
        "AgentEvent",
        "AgentHook",
        "AsyncEventStream",
        "CallbackHook",
        "DEFAULT_STREAM_QUEUE_SIZE",
        "EventCallback",
        "EventRecorder",
        "FINAL_RESULT",
        "HookInput",
        "ITERATION_FINISHED",
        "ITERATION_STARTED",
        "MODEL_REQUEST_STARTED",
        "MODEL_RESPONSE_FINISHED",
        "MODEL_STREAM_CONTENT_DELTA",
        "MODEL_STREAM_REASONING_DELTA",
        "MODEL_STREAM_RECOVERED",
        "MODEL_STREAM_REFUSAL_DELTA",
        "MODEL_STREAM_TOOL_CALL_DELTA",
        "RUN_ERROR",
        "RUN_FINISHED",
        "RUN_STARTED",
        "TOOL_CALL_FINISHED",
        "TOOL_CALL_STARTED",
        "TOOL_CALLS_FINISHED",
        "TOOL_CALLS_STARTED",
        "TURN_CONTEXT_BUILT",
        "TURN_ERROR",
        "TURN_FINISHED",
        "TURN_STARTED",
    },
    bumblehive.protocols: {
        "AgentError",
        "GenerationConfig",
        "MCPServerConfig",
        "Message",
        "ToolCall",
        "ToolResult",
        "UserMessage",
        "normalize_user_message",
        "parse_tool_call",
    },
    bumblehive.providers: {
        "ModelProvider",
        "ModelRequest",
        "ModelResponse",
        "ModelStreamCallbacks",
        "OpenAIChatCompletionsProvider",
        "ProviderManager",
        "RetryConfig",
    },
    bumblehive.session: set(),
    bumblehive.session.stores: set(),
    bumblehive.skills: {
        "Skill",
        "SkillError",
        "SkillLoadResult",
        "SkillsManager",
        "render_skills_summary",
    },
    bumblehive.tools: {
        "CallableTool",
        "MCPServerStatus",
        "PathAllowlist",
        "Tool",
        "ToolManager",
        "ToolRegistry",
    },
    bumblehive.tools.adapters: {
        "CallableTool",
    },
    bumblehive.tools.builtins: set(),
    bumblehive.tools.mcp: set(),
}
