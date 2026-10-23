import assert from "node:assert/strict";
import { before, test } from "node:test";
import { server } from "../../helpers/vite.mjs";

let sidebarTree;

before(async () => {
  sidebarTree = await server.ssrLoadModule("/src/components/sidebar/session-tree.ts");
});

test("buildWorkspaceGroups nests children and preserves matching ancestors", () => {
  const workspaces = [{ path: "/workspace", createdAt: 1 }];
  const sessions = [
    {
      session_id: "parent",
      parent_session_id: null,
      workspace: "/workspace",
      title: "父会话",
      last_message: "",
      message_count: 1,
      created_at: 1,
      updated_at: 1,
    },
    {
      session_id: "child",
      parent_session_id: "parent",
      workspace: "/workspace",
      title: "Bee 性能分析",
      last_message: "",
      message_count: 1,
      created_at: 2,
      updated_at: 2,
    },
  ];

  const groups = sidebarTree.buildWorkspaceGroups(
    workspaces,
    sessions,
    [],
    "性能",
  );

  assert.equal(groups.length, 1);
  assert.equal(groups[0].sessions.length, 1);
  assert.equal(groups[0].sessions[0].id, "parent");
  assert.equal(groups[0].sessions[0].children[0].id, "child");
});
