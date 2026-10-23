import assert from "node:assert/strict";
import { before, test } from "node:test";
import { server } from "../helpers/vite.mjs";

let sessionTree;

before(async () => {
  sessionTree = await server.ssrLoadModule("/src/lib/session-tree.ts");
});

test("sessionBranchIds includes every descendant exactly once", () => {
  const sessions = [
    { session_id: "parent", parent_session_id: null },
    { session_id: "child", parent_session_id: "parent" },
    { session_id: "grandchild", parent_session_id: "child" },
    { session_id: "other", parent_session_id: null },
  ];
  const pending = new Map([
    [
      "pending-child",
      {
        workspace: "/workspace",
        parentSessionId: "parent",
      },
    ],
  ]);

  assert.deepEqual(
    [...sessionTree.sessionBranchIds("parent", sessions, pending)].sort(),
    ["child", "grandchild", "parent", "pending-child"],
  );
});
