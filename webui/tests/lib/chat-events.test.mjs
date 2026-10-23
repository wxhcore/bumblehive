import assert from "node:assert/strict";
import { before, test } from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { server } from "../helpers/vite.mjs";
import { approvalFrame } from "../fixtures/approval.mjs";

let toolActivityList;
let assistantMessage;
let chatEvents;

before(async () => {
  toolActivityList = await server.ssrLoadModule("/src/components/chat/ToolActivityList.tsx");
  assistantMessage = await server.ssrLoadModule("/src/components/chat/AssistantMessage.tsx");
  chatEvents = await server.ssrLoadModule("/src/lib/chat-events.ts");
});

function toolEvent(kind, callId = "call-1", error) {
  return {
    type: "event", kind, run_id: "run-1", session_id: "session-1",
    iteration: 0, timestamp: 1,
    payload: kind === "tool.call.started"
      ? { tool_call: { call_id: callId, name: "write_file", arguments: { path: "/outside.txt", content: "hello" } } }
      : { tool_result: { tool_call_id: callId, name: "write_file" }, ok: !error, error },
  };
}

function emptyAssistant() {
  return [{ id: "assistant", role: "assistant", content: "", iterations: [] }];
}

function allTools(messages) {
  return messages[0].iterations.flatMap((item) => item.tools ?? []);
}

test("historyMessages restores assistant iterations and tool results", () => {
  const messages = chatEvents.historyMessages([
    { role: "user", content: "检查项目" },
    {
      role: "assistant",
      content: "",
      reasoning_content: "先读取目录",
      tool_calls: [
        {
          id: "call-1",
          function: { name: "list_dir", arguments: '{"path":"."}' },
        },
      ],
    },
    {
      role: "tool",
      tool_call_id: "call-1",
      content: { entries: ["README.md"] },
    },
    { role: "assistant", content: "项目检查完成" },
  ]);

  assert.equal(messages.length, 2);
  assert.equal(messages[0].content, "检查项目");
  assert.equal(messages[1].iterations.length, 2);
  assert.equal(messages[1].iterations[0].reasoning, "先读取目录");
  assert.equal(messages[1].iterations[0].tools[0].status, "completed");
  assert.equal(messages[1].iterations[1].content, "项目检查完成");
});

test("stream frames are merged, budgeted, and applied in order", () => {
  const first = {
    type: "event",
    kind: "model.stream.content_delta",
    run_id: "run-1",
    payload: { delta: "你好" },
    iteration: 0,
    session_id: "session-1",
    timestamp: 1,
  };
  const second = {
    ...first,
    payload: { delta: "，Bee" },
    timestamp: 2,
  };
  const queued = [first];
  chatEvents.appendPendingAgentFrame(queued, second);

  assert.equal(queued.length, 1);
  assert.equal(queued[0].payload.delta, "你好，Bee");

  const { painted, textCount } = chatEvents.takeAgentFramesForPaint(queued, 3);
  assert.equal(textCount, 3);
  assert.equal(painted[0].payload.delta, "你好，");
  assert.equal(queued[0].payload.delta, "Bee");

  const updated = chatEvents.applyAgentEventFrames(
    [
      {
        id: "assistant-1",
        role: "assistant",
        content: "",
        iterations: [],
      },
    ],
    "assistant-1",
    painted,
  );
  assert.equal(updated[0].iterations[0].content, "你好，");
});

test("approval survives a delayed start and rejection remains terminal", () => {
  const request = approvalFrame();
  let messages = chatEvents.applyApprovalFrame(emptyAssistant(), "assistant", request);
  messages = chatEvents.applyAgentEventFrames(messages, "assistant", [toolEvent("tool.call.started")]);
  assert.equal(allTools(messages).length, 1);
  assert.equal(allTools(messages)[0].status, "waiting_approval");
  messages = chatEvents.applyApprovalFrame(messages, "assistant", { ...request, type: "approval_resolved", approved: false });
  messages = chatEvents.applyAgentEventFrames(messages, "assistant", [
    toolEvent("tool.call.finished", "call-1", { code: "tool_approval_denied", message: "拒绝" }),
    toolEvent("tool.call.started"),
  ]);
  assert.equal(allTools(messages)[0].status, "rejected");
  assert.equal(chatEvents.completeIterationTools(messages[0].iterations, "completed")[0].tools[0].status, "rejected");
  const html = renderToStaticMarkup(createElement(toolActivityList.ToolSteps, { tools: allTools(messages) }));
  assert.match(html, /已拒绝/);
});

test("approvals correlate parallel calls by id and fast completion wins over acknowledgement", () => {
  let messages = chatEvents.applyAgentEventFrames(emptyAssistant(), "assistant", [toolEvent("tool.call.started", "call-1")]);
  messages = chatEvents.applyApprovalFrame(messages, "assistant", approvalFrame("call-2"));
  messages = chatEvents.applyApprovalFrame(messages, "assistant", approvalFrame("call-1"));
  assert.deepEqual(allTools(messages).map((tool) => [tool.id, tool.status]), [
    ["call-1", "waiting_approval"], ["call-2", "waiting_approval"],
  ]);
  messages = chatEvents.applyApprovalFrame(messages, "assistant", { ...approvalFrame("call-1"), type: "approval_resolved", approved: true });
  assert.equal(allTools(messages)[0].status, "running");
  messages = chatEvents.applyAgentEventFrames(messages, "assistant", [toolEvent("tool.call.finished", "call-1")]);
  messages = chatEvents.applyApprovalFrame(messages, "assistant", { ...approvalFrame("call-1"), type: "approval_resolved", approved: true });
  assert.equal(allTools(messages)[0].status, "completed");
  assert.equal(allTools(messages)[1].status, "waiting_approval");
  assert.equal(chatEvents.completeIterationTools(messages[0].iterations, "cancelled")[0].tools[1].status, "cancelled");
});

test("history restores rejected tool calls", () => {
  const messages = chatEvents.historyMessages([
    { role: "assistant", tool_calls: [{ id: "call-1", function: { name: "write_file", arguments: "{}" } }] },
    { role: "tool", tool_call_id: "call-1", content: JSON.stringify({ error: { code: "tool_approval_denied", message: "用户拒绝" } }) },
  ]);
  assert.equal(allTools(messages)[0].status, "rejected");
});

test("history shows interrupted calls as stopped while preserving recorded results", () => {
  const messages = chatEvents.historyMessages([
    { role: "user", content: "Write files" },
    {
      role: "assistant",
      tool_calls: ["finished", "failed", "interrupted"].map((id) => ({
        id,
        function: {
          name: "write_file",
          arguments: JSON.stringify({ path: `${id}.txt`, content: "hello" }),
        },
      })),
    },
    { role: "tool", tool_call_id: "finished", content: { success: true } },
    { role: "tool", tool_call_id: "failed", content: { error: "Permission denied" } },
    { role: "user", content: "Continue after reconnecting" },
    { role: "assistant", content: "Ready" },
  ]);
  const tools = messages[1].iterations[0].tools;
  assert.deepEqual(tools.map((tool) => [tool.id, tool.status]), [
    ["finished", "completed"],
    ["failed", "error"],
    ["interrupted", "cancelled"],
  ]);
  const html = renderToStaticMarkup(
    createElement(toolActivityList.ToolSteps, { tools: [tools[2]] }),
  );
  assert.match(html, /写入文件已停止/);
  assert.doesNotMatch(html, /正在写入文件/);
});

test("history keeps a stopped approval cancelled after recovery fills the missing result", () => {
  const messages = chatEvents.historyMessages([
    { role: "user", content: "Run a command" },
    { role: "assistant", tool_calls: [{ id: "stopped", function: {
      name: "exec", arguments: JSON.stringify({ command: "printf STOP_SHOULD_NOT_RUN" }),
    } }] },
    { role: "tool", tool_call_id: "stopped", name: "exec",
      content: "[Tool result unavailable - call was interrupted or lost]" },
    { role: "assistant", content: "[Previous turn was interrupted after tool execution.]" },
    { role: "user", content: "Continue without running the command" },
    { role: "assistant", content: "Ready" },
  ]);
  const tools = messages[1].iterations.flatMap((iteration) => iteration.tools ?? []);
  assert.equal(tools.length, 1);
  assert.equal(tools[0].status, "cancelled");
  const html = renderToStaticMarkup(createElement(toolActivityList.ToolSteps, { tools }));
  assert.match(html, /Shell 命令已停止/);
  assert.doesNotMatch(html, /已运行 Shell 命令/);
});

test("reconnect restores live tools, elapsed time and approval without duplicating the original input", () => {
  const original = "查询课程";
  const stored = [
    { role: "user", content: original },
    { role: "assistant", tool_calls: [{ id: "live", function: { name: "query", arguments: "{}" } }] },
    { role: "user", content: "后来插入的引导" },
  ];
  const ready = {
    type: "ready", session_id: "one", running: true, started_at: 123,
    active_message: { message_id: "A", content: original }, approvals: [],
  };
  const restored = chatEvents.restoreRunningMessages(chatEvents.historyMessages(stored), ready);
  assert.equal(restored.filter((message) => message.content === original).length, 1);
  assert.equal(restored.at(-1).startedAt, 123000);
  const waitingHistory = chatEvents.historyMessages(stored.slice(0, 2));
  const running = chatEvents.restoreRunningMessages(waitingHistory, ready);
  assert.equal(running.at(-1).iterations[0].tools[0].status, "running");
  const approval = { ...approvalFrame(), call_id: "live" };
  const waiting = chatEvents.restoreRunningMessages(waitingHistory, { ...ready, approvals: [approval] });
  assert.equal(waiting.at(-1).iterations[0].tools[0].status, "waiting_approval");
  assert.equal(waiting.at(-1).startedAt, 123000);
});

test("steering after tools stays in one execution process while follow-ups remain separate turns", () => {
  const stored = [
    { role: "user", content: "你好" },
    { role: "assistant", content: "我先看看目录", tool_calls: [
      { id: "dir", function: { name: "list_dir", arguments: '{"path":"."}' } },
    ] },
    { role: "tool", tool_call_id: "dir", content: { entries: [] } },
    { role: "user", content: "在干嘛" },
    { role: "user", content: "用中文简短说" },
    { role: "assistant", content: "目录检查完成" },
    { role: "user", content: "下一轮：继续检查" },
    { role: "assistant", content: "下一轮完成" },
  ];
  const messages = chatEvents.historyMessages(stored);
  assert.deepEqual(messages.map((message) => message.role), ["user", "assistant", "user", "assistant"]);
  assert.equal(messages[2].content, "下一轮：继续检查");
  const firstRun = messages[1];
  assert.deepEqual(firstRun.iterations.map((item) => item.kind ?? "model"), ["model", "steering", "steering", "model"]);
  assert.deepEqual(firstRun.iterations.slice(1, 3).map((item) => item.content), ["在干嘛", "用中文简短说"]);
  const closed = renderToStaticMarkup(createElement(assistantMessage.MessageView, { message: firstRun, active: false }));
  assert.match(closed, /已结束/);
  assert.match(closed, /目录检查完成/);
  assert.doesNotMatch(closed, /在干嘛|用中文简短说|我先看看目录/);
  assert.equal((closed.match(/execution-process-toggle/g) ?? []).length, 1);
  const opened = renderToStaticMarkup(createElement(assistantMessage.MessageView, { message: firstRun, active: true }));
  assert.match(opened, /aria-label="引导消息"/);
  assert.ok(opened.indexOf("我先看看目录") < opened.indexOf("在干嘛"));
  assert.ok(opened.indexOf("在干嘛") < opened.indexOf("用中文简短说"));
  assert.ok(opened.indexOf("用中文简短说") < opened.indexOf("目录检查完成"));
  assert.equal(stored[3].role, "user");
  assert.equal(stored[3].content, "在干嘛");
});

test("merged steering and repeated tool calls stay ordered across history reloads", () => {
  const stored = [
    { role: "user", content: "分析项目" },
    { role: "assistant", tool_calls: [{ id: "first", function: { name: "list_dir", arguments: "{}" } }] },
    { role: "tool", tool_call_id: "first", content: "first result" },
    { role: "user", content: "第一条引导\n\n第二条引导" },
    { role: "assistant", tool_calls: [{ id: "second", function: { name: "read_file", arguments: "{}" } }] },
    { role: "tool", tool_call_id: "second", content: "second result" },
    { role: "user", content: "第三条引导" },
    { role: "assistant", content: "最终回答", _bumblehive_ui: { duration_s: 11 } },
  ];
  const restored = chatEvents.historyMessages(JSON.parse(JSON.stringify(stored)));
  assert.equal(restored.length, 2);
  assert.equal(restored[1].durationSeconds, 11);
  assert.deepEqual(restored[1].iterations.map((item) => item.kind ?? "model"), ["model", "steering", "model", "steering", "model"]);
  assert.equal(restored[1].iterations[0].tools[0].status, "completed");
  assert.equal(restored[1].iterations[2].tools[0].status, "completed");
});

test("restored steering receipts reinsert original IDs at their queue positions", () => {
  const queued = (message_id, position) => ({ type: "message_status", session_id: "one", status: "queued", message_id, content: "same text", position });
  let items = [
    { message_id: "left", content: "first follow-up" },
    { message_id: "tail", content: "last follow-up" },
    { message_id: "new", content: "optimistic new input", submitting: true },
  ];
  items = chatEvents.applyPendingMessageStatus(items, queued("B", 1));
  items = chatEvents.applyPendingMessageStatus(items, queued("C", 2));
  assert.deepEqual(items.map((item) => item.message_id), ["left", "B", "C", "tail", "new"]);
  assert.equal(items[1].content, items[2].content);
  assert.equal(items[1].submitting, undefined);
  items = chatEvents.applyPendingMessageStatus(items, queued("C", 2));
  assert.deepEqual(items.map((item) => item.message_id), ["left", "B", "C", "tail", "new"]);
  items = chatEvents.applyPendingMessageStatus(items, { ...queued("B"), status: "started" });
  assert.deepEqual(items.map((item) => item.message_id), ["left", "C", "tail", "new"]);
  items = chatEvents.applyPendingMessageStatus(items, { ...queued("new"), content: "acknowledged" });
  assert.deepEqual(items.map((item) => item.message_id), ["left", "C", "tail", "new"]);
  assert.equal(items.at(-1).submitting, undefined);
});

test("sub-agent history keeps task text separate from model-only handoff instructions", () => {
  const messages = chatEvents.historyMessages([
    { role: "user", content: "Internal instructions\nTask:\nReview", _bumblehive_ui: { content: "Review" } },
    { role: "assistant", content: "Conclusion" },
  ]);
  assert.equal(messages[0].content, "Review");
  const restored = chatEvents.restoreRunningMessages(messages.slice(0, 1), {
    type: "ready", session_id: "child", running: true, started_at: 123,
    active_message: { message_id: "child", content: "Review" },
  });
  assert.equal(restored.filter((message) => message.role === "user").length, 1);
  assert.equal(restored.at(-1).startedAt, 123000);
});
