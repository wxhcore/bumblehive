import assert from "node:assert/strict";
import { before, test } from "node:test";
import { server } from "../helpers/vite.mjs";

let workspaces;

before(async () => {
  workspaces = await server.ssrLoadModule("/src/lib/workspaces.ts");
});

test("saving unrelated settings does not switch to another workspace", () => {
  assert.equal(
    workspaces.workspaceSettingChanged("/workspace/default", "/workspace/default"),
    false,
  );
  assert.equal(
    workspaces.workspaceSettingChanged("/workspace/default", "/workspace/next"),
    true,
  );
});
