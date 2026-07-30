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

export function toolIsEnabled(
  selected: string[] | null,
  name: string,
): boolean {
  return selected === null || selected.includes(name);
}

export function setToolsEnabled(
  selected: string[] | null,
  targetNames: string[],
  enabled: boolean,
  availableNames: string[],
): string[] | null {
  if (!targetNames.length) return selected;

  const targets = new Set(targetNames);
  const next =
    selected === null ? new Set(availableNames) : new Set(selected);

  for (const name of targets) {
    if (enabled) next.add(name);
    else next.delete(name);
  }

  if (enabled && availableNames.every((name) => next.has(name))) {
    return null;
  }
  return Array.from(next);
}
