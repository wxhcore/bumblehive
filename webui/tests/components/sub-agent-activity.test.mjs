import assert from "node:assert/strict";
import { before, test } from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { server } from "../helpers/vite.mjs";

let chatEvents;

before(async () => {
  chatEvents = await server.ssrLoadModule("/src/lib/chat-events.ts");
});

test("background delegation displays startup instead of falsely claiming completion", async () => {
  const { SubAgentActivity } = await server.ssrLoadModule("/src/components/SubAgentActivity.tsx");
  const background = { id: "bg", name: "sub_agent", arguments: { title: "Review", task: "Read files" }, taskId: "bg", status: "completed" };
  const single = renderToStaticMarkup(createElement(SubAgentActivity, { tools: [background] }));
  assert.match(single, /已启动后台 Bee/);
  assert.doesNotMatch(single, /Bee 已完成/);
  const group = renderToStaticMarkup(createElement(SubAgentActivity, { tools: [background, { ...background, id: "bg2" }] }));
  assert.match(group, /2 个后台已启动/);
  assert.doesNotMatch(group, /全部完成|协作完成/);
  const mixed = renderToStaticMarkup(createElement(SubAgentActivity, { tools: [background, { ...background, id: "old-sync", taskId: undefined, arguments: { title: "Old", task: "Read" } }] }));
  assert.match(mixed, /1 个后台已启动/);
  assert.match(mixed, /1 完成/);
});

test("pending task envelopes render live and restored; old histories retain their meaning", async () => {
  const { SubAgentActivity } = await server.ssrLoadModule("/src/components/SubAgentActivity.tsx");
  const cases = [
    [{ status: "pending", task_id: "delegate" }, true],
    [{ session_id: "child", background: true }, true],
    ["Child final answer", false],
  ];
  for (const [value, background] of cases) {
    const content = typeof value === "string" ? value : JSON.stringify(value);
    const messages = chatEvents.historyMessages([
      { role: "assistant", content: "", tool_calls: [{ id: "delegate", function: {
        name: "sub_agent", arguments: JSON.stringify({ title: "Review", task: "Read files" }),
      } }] },
      { role: "tool", tool_call_id: "delegate", content },
    ]);
    const restored = messages[0].iterations[0].tools[0];
    const html = renderToStaticMarkup(createElement(SubAgentActivity, { tools: [restored] }));
    assert.equal(restored.taskId, background ? "delegate" : undefined);
    assert.match(html, background ? /已启动后台 Bee/ : /Bee 已完成/);
    assert.doesNotMatch(html, background ? /Bee 已完成/ : /已启动后台 Bee/);
  }
  const live = chatEvents.applyAgentEventFrames([
    { id: "assistant", role: "assistant", content: "", iterations: [] },
  ], "assistant", [{
    type: "event", kind: "tool.call.finished", run_id: "run", session_id: "parent",
    iteration: 0, timestamp: 1, payload: {
      ok: true, tool_result: { tool_call_id: "delegate", name: "sub_agent", status: "pending", task_id: "delegate" },
    },
  }])[0].iterations[0].tools[0];
  assert.equal(live.taskId, "delegate");
  const html = renderToStaticMarkup(createElement(SubAgentActivity, { tools: [live] }));
  assert.match(html, /已启动后台 Bee/);
  assert.doesNotMatch(html, /Bee 已完成/);
});
