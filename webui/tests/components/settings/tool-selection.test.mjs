import assert from "node:assert/strict";
import { before, test } from "node:test";
import { server } from "../../helpers/vite.mjs";

let toolSelection;

before(async () => {
  toolSelection = await server.ssrLoadModule("/src/components/settings/tool-selection.ts");
});

test("tool sources group MCP tools by their configured server", () => {
  const groups = toolSelection.buildToolSourceGroups(
    [
      {
        name: "apply_patch",
        description: "Edit files",
        source: "local",
        parallel_safe: false,
      },
      {
        name: "github_search",
        description: "Search GitHub",
        source: "mcp",
        parallel_safe: true,
      },
      {
        name: "filesystem_read",
        description: "Read a file",
        source: "mcp",
        parallel_safe: true,
      },
    ],
    [
      { name: "GitHub", url: "https://github.test/mcp", headers: {} },
      { name: "Filesystem", url: "https://files.test/mcp", headers: {} },
    ],
    [
      {
        name: "GitHub",
        connected: true,
        registered_tools: ["github_search"],
      },
      {
        name: "Filesystem",
        connected: true,
        registered_tools: ["filesystem_read"],
      },
    ],
  );

  assert.deepEqual(
    groups.map((group) => ({
      id: group.id,
      name: group.name,
      tools: group.tools.map((tool) => tool.name),
    })),
    [
      { id: "local", name: "内置工具", tools: ["apply_patch"] },
      { id: "mcp:0", name: "GitHub", tools: ["github_search"] },
      { id: "mcp:1", name: "Filesystem", tools: ["filesystem_read"] },
    ],
  );
});
