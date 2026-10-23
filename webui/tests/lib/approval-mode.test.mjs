import assert from "node:assert/strict";
import { test } from "node:test";
import { server } from "../helpers/vite.mjs";

test("approval preference persists and defaults to requesting approval", async () => {
  const preference = await server.ssrLoadModule("/src/lib/approval-mode.ts");
  const previousWindow = globalThis.window;
  const storage = new Map();
  globalThis.window = { localStorage: {
    getItem: (key) => storage.get(key) ?? null,
    setItem: (key, value) => storage.set(key, value),
  } };
  try {
    assert.equal(preference.readApprovalMode(), "request");
    preference.writeApprovalMode("full_access");
    assert.equal(preference.readApprovalMode(), "full_access");
    preference.writeApprovalMode("request");
    assert.equal(preference.readApprovalMode(), "request");
    storage.set("bumblehive.approval-mode.v1", "invalid");
    assert.equal(preference.readApprovalMode(), "request");
  } finally {
    if (previousWindow === undefined) delete globalThis.window;
    else globalThis.window = previousWindow;
  }
});
