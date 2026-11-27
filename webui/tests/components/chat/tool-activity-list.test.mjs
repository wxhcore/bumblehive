import assert from "node:assert/strict";
import { before, test } from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { server } from "../../helpers/vite.mjs";

let toolActivityList;

before(async () => {
  toolActivityList = await server.ssrLoadModule("/src/components/chat/ToolActivityList.tsx");
});

test("send_message folds the full literal text under the addressed worker or main agent", async () => {
  const { ChatView } = await server.ssrLoadModule("/src/components/ChatView.tsx");
  const { historyMessages } = await server.ssrLoadModule("/src/lib/chat-events.ts");
  const message = "第一行\n\n" + "正文".repeat(90) + " <script> 原样结束";
  for (const [target, recipient] of [["delegated-id", "发给「创建游戏页面」"], ["parent", "发给主 Agent"], ["old-id", "发给 Worker"]]) {
    const messages = historyMessages([
      { role: "assistant", tool_calls: [{ id: "original-call", function: { name: "sub_agent", arguments: '{"title":"创建游戏页面"}' } }] },
      { role: "tool", tool_call_id: "original-call", content: '{"status":"pending","task_id":"delegated-id"}' },
      { role: "assistant", content: "已派工" },
      { role: "user", content: "继续" },
      { role: "assistant", tool_calls: [{ id: "msg", function: { name: "send_message", arguments: JSON.stringify({ target, message }) } }] },
      { role: "tool", tool_call_id: "msg", content: '{"status":"sent"}' },
    ]);
    const html = renderToStaticMarkup(createElement(ChatView, { messages, isStreaming: true }));
    const row = html.match(/<details class="agent-message"><summary[^>]*>(.*?)<\/summary>([\s\S]*?)<\/details>/s);
    assert.ok(row);
    assert.match(row[1], /bumblehive-bee\.png/);
    assert.ok(row[1].includes(recipient));
    assert.doesNotMatch(row[1], /第一行|delegated-id|old-id|target:|message:/);
    assert.ok(row[2].includes(message.replace("<script>", "&lt;script&gt;")));
    assert.equal(row[2].includes("任务 ID：old-id"), target === "old-id");
  }
});

test("pending and rejected terminal input stays separate from the running process", () => {
  for (const status of ["waiting_approval", "rejected"]) {
    const iterations = [{ id: "iteration", iteration: 0, content: "", tools: [
      { id: "exec", name: "exec", status: "running", detail: { kind: "shell", sessionId: "terminal", running: true } },
      { id: "input", name: "write_stdin", status, arguments: { session_id: "terminal", chars: "exit" } },
    ] }];
    const normalized = toolActivityList.consolidateShellIterations(iterations);
    assert.equal(normalized[0].tools.length, 2);
    assert.equal(normalized[0].tools[1].status, status);
  }
});
