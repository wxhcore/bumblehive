import type {
  McpServerSettings,
  McpServerStatus,
  SettingsToolOption,
} from "../../types/api";

export interface ToolSourceGroup {
  id: string;
  name: string;
  kind: "local" | "mcp";
  connected: boolean | null;
  serverIndex: number | null;
  tools: SettingsToolOption[];
}

export function buildToolSourceGroups(
  tools: SettingsToolOption[],
  servers: McpServerSettings[],
  statuses: McpServerStatus[],
): ToolSourceGroup[] {
  const localTools = tools.filter((tool) => tool.source === "local");
  const mcpTools = tools.filter((tool) => tool.source === "mcp");
  const claimed = new Set<string>();
  const groups: ToolSourceGroup[] = [
    {
      id: "local",
      name: "内置工具",
      kind: "local",
      connected: null,
      serverIndex: null,
      tools: localTools,
    },
  ];

  servers.forEach((server, serverIndex) => {
    const status = statuses.find((item) => item.name === server.name);
    const registered = new Set(status?.registered_tools ?? []);
    const serverTools = mcpTools.filter(
      (tool) => registered.has(tool.name) && !claimed.has(tool.name),
    );
    serverTools.forEach((tool) => claimed.add(tool.name));
    groups.push({
      id: `mcp:${serverIndex}`,
      name: server.name.trim() || "未命名 MCP 服务",
      kind: "mcp",
      connected: status?.connected ?? false,
      serverIndex,
      tools: serverTools,
    });
  });

  const unclaimed = mcpTools.filter((tool) => !claimed.has(tool.name));
  if (unclaimed.length) {
    groups.push({
      id: "mcp:other",
      name: "其他 MCP 工具",
      kind: "mcp",
      connected: null,
      serverIndex: null,
      tools: unclaimed,
    });
  }

  return groups;
}
