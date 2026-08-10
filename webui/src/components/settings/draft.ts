import type {
  McpServerSettings,
  Settings,
  SettingsUpdate,
} from "../../types/api";
import { DEFAULT_CONFIG_VALUES } from "../../lib/default-settings";

export interface SettingsDraft {
  provider: {
    type: string;
    model: string;
    baseUrl: string;
  };
  generation: {
    maxCompletionTokens: number | null;
    temperature: number | null;
    thinkingEnabled: boolean;
    reasoningEffort: string;
  };
  context: {
    instructions: string;
    dynamicContextJson: string;
    skillNames: string[] | null;
    toolNames: string[] | null;
  };
  runtime: {
    workspace: string;
    timezone: string;
    contextWindowTokens: number | null;
    maxToolResultChars: number | null;
    maxIterations: number | null;
    extraReadRoots: string[];
    extraWriteRoots: string[];
    restrictExecPaths: boolean;
  };
  mcpServers: McpServerSettings[];
}

export function settingsToDraft(
  settings: Settings,
  fallbackTimezone = "",
): SettingsDraft {
  const thinking = settings.generation.extra_body?.thinking;
  const thinkingDisabled = Boolean(
    thinking &&
    !Array.isArray(thinking) &&
    typeof thinking === "object" &&
    (thinking as Record<string, unknown>).type === "disabled",
  );

  return {
    provider: {
      type: settings.provider.type || DEFAULT_CONFIG_VALUES.provider.type,
      model: settings.provider.model ?? "",
      baseUrl: settings.provider.base_url ?? "",
    },
    generation: {
      maxCompletionTokens:
        settings.generation.max_completion_tokens ??
        DEFAULT_CONFIG_VALUES.generation.maxCompletionTokens,
      temperature: settings.generation.temperature ?? null,
      thinkingEnabled: !thinkingDisabled,
      reasoningEffort: thinkingDisabled
        ? ""
        : (settings.generation.reasoning_effort ?? ""),
    },
    context: {
      instructions: settings.agent.instructions ?? "",
      dynamicContextJson: JSON.stringify(
        settings.agent.dynamic_context ?? {},
        null,
        2,
      ),
      skillNames: settings.agent.skill_names ?? null,
      toolNames: settings.agent.tool_names ?? null,
    },
    runtime: {
      workspace: settings.runtime.workspace ?? "",
      timezone: settings.runtime.timezone ?? fallbackTimezone,
      contextWindowTokens:
        settings.runtime.context_window_tokens ??
        DEFAULT_CONFIG_VALUES.runtime.contextWindowTokens,
      maxToolResultChars:
        settings.runtime.max_tool_result_chars ??
        DEFAULT_CONFIG_VALUES.runtime.maxToolResultChars,
      maxIterations:
        settings.runtime.max_iterations ??
        DEFAULT_CONFIG_VALUES.runtime.maxIterations,
      extraReadRoots: settings.runtime.extra_read_roots ?? [],
      extraWriteRoots: settings.runtime.extra_write_roots ?? [],
      restrictExecPaths:
        settings.runtime.restrict_exec_paths ??
        DEFAULT_CONFIG_VALUES.runtime.restrictExecPaths,
    },
    mcpServers: settings.mcp_servers.map((server) => ({
      name: server.name,
      url: server.url,
      headers: { ...server.headers },
    })),
  };
}

function parseJsonObject(
  text: string,
  fieldName: string,
): Record<string, unknown> {
  const value = text.trim();
  try {
    const parsed = JSON.parse(value || "{}") as unknown;
    if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") {
      throw new Error();
    }
    return parsed as Record<string, unknown>;
  } catch {
    throw new Error(`${fieldName}必须是有效的 JSON 对象`);
  }
}

export function draftToUpdate(
  draft: SettingsDraft,
  apiKey: string,
): SettingsUpdate {
  const model = draft.provider.model.trim();
  if (!model) throw new Error("模型名称不能为空");
  if (
    draft.generation.maxCompletionTokens !== null &&
    draft.generation.maxCompletionTokens < 1
  ) {
    throw new Error("最大输出 Token 必须大于 0");
  }
  if (
    draft.generation.temperature !== null &&
    draft.generation.temperature < 0
  ) {
    throw new Error("Temperature 不能小于 0");
  }
  if (
    draft.runtime.contextWindowTokens !== null &&
    draft.runtime.contextWindowTokens < 1
  ) {
    throw new Error("上下文窗口必须大于 0");
  }
  if (
    draft.runtime.maxToolResultChars !== null &&
    draft.runtime.maxToolResultChars < 1
  ) {
    throw new Error("工具结果字符上限必须大于 0");
  }
  if (
    draft.runtime.maxIterations !== null &&
    draft.runtime.maxIterations < 1
  ) {
    throw new Error("最大迭代次数必须大于 0");
  }

  const provider: NonNullable<SettingsUpdate["provider"]> = {
    type: draft.provider.type,
    model,
    base_url: draft.provider.baseUrl.trim() || null,
  };
  if (apiKey.trim()) provider.api_key = apiKey.trim();

  const mcpServers = draft.mcpServers.map((server, index) => {
    const name = server.name.trim();
    const url = server.url.trim();
    if (!name) throw new Error(`第 ${index + 1} 个 MCP 服务缺少名称`);
    if (!url) throw new Error(`MCP 服务“${name}”缺少 URL`);
    return {
      name,
      url,
      headers: Object.fromEntries(
        Object.entries(server.headers)
          .map(([key, value]) => [key.trim(), value] as const)
          .filter(([key]) => Boolean(key)),
      ),
    };
  });
  if (new Set(mcpServers.map((server) => server.name)).size !== mcpServers.length) {
    throw new Error("MCP 服务名称不能重复");
  }

  return {
    provider,
    generation: {
      max_completion_tokens: draft.generation.maxCompletionTokens,
      temperature: draft.generation.temperature,
      reasoning_effort: draft.generation.thinkingEnabled
        ? draft.generation.reasoningEffort.trim() || null
        : null,
      extra_body: draft.generation.thinkingEnabled
        ? null
        : { thinking: { type: "disabled" } },
    },
    agent: {
      instructions: draft.context.instructions.trim() || null,
      dynamic_context: parseJsonObject(
        draft.context.dynamicContextJson,
        "动态上下文",
      ),
      skill_names: draft.context.skillNames,
      tool_names: draft.context.toolNames,
    },
    runtime: {
      workspace: draft.runtime.workspace.trim() || null,
      timezone: draft.runtime.timezone.trim() || null,
      context_window_tokens: draft.runtime.contextWindowTokens,
      max_tool_result_chars: draft.runtime.maxToolResultChars,
      max_iterations: draft.runtime.maxIterations,
      extra_read_roots: draft.runtime.extraReadRoots
        .map((path) => path.trim())
        .filter(Boolean),
      extra_write_roots: draft.runtime.extraWriteRoots
        .map((path) => path.trim())
        .filter(Boolean),
      restrict_exec_paths: draft.runtime.restrictExecPaths,
    },
    mcp_servers: mcpServers,
  };
}

export function draftSignature(
  draft: SettingsDraft,
  apiKey: string,
): string {
  return JSON.stringify({ draft, apiKey });
}
