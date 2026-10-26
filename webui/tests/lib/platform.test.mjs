import assert from "node:assert/strict";
import { test } from "node:test";
import { server } from "../helpers/vite.mjs";

test("native confirmation waits for a decision and fails closed", async () => {
  const previousWindow = globalThis.window;
  let decide;
  const calls = [];
  globalThis.window = { __TAURI_INTERNALS__: { invoke: (command, args) => {
    calls.push({ command, args });
    return new Promise((resolve) => { decide = resolve; });
  } } };
  try {
    const { confirmAction } = await server.ssrLoadModule("/src/lib/platform.ts");
    let settled = false;
    const pending = confirmAction("放弃更改？").then((value) => { settled = true; return value; });
    await Promise.resolve();
    assert.equal(settled, false);
    assert.equal(calls[0].command, "plugin:dialog|message");
    assert.equal(calls[0].args.buttons, "OkCancel");
    decide("Cancel");
    assert.equal(await pending, false);
    const approved = confirmAction("放弃更改？");
    decide("Ok");
    assert.equal(await approved, true);
    globalThis.window.__TAURI_INTERNALS__.invoke = async () => { throw new Error("dialog unavailable"); };
    assert.equal(await confirmAction("放弃更改？"), false);
    delete globalThis.window.__TAURI_INTERNALS__;
    globalThis.window.confirm = () => false;
    assert.equal(await confirmAction("取消"), false);
    globalThis.window.confirm = () => true;
    assert.equal(await confirmAction("确认"), true);
  } finally {
    if (previousWindow === undefined) delete globalThis.window;
    else globalThis.window = previousWindow;
  }
});
