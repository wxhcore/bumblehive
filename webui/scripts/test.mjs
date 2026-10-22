import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createServer } from "vite";

let server;
let approvalCard;
let toolActivityList;
let assistantMessage;
let chatEvents;
let markdownContent;
let optionSelection;
let sessionTree;
let sidebarTree;
let settingsDraft;
let settingsView;
let toolSelection;
let workspaces;

before(async () => {
  server = await createServer({
    appType: "custom",
    logLevel: "silent",
    server: { middlewareMode: true },
  });
  [
    approvalCard,
    toolActivityList,
    assistantMessage,
    chatEvents,
    markdownContent,
    optionSelection,
    sessionTree,
    sidebarTree,
    settingsDraft,
    settingsView,
    toolSelection,
    workspaces,
  ] =
    await Promise.all([
      server.ssrLoadModule("/src/components/ApprovalCard.tsx"),
      server.ssrLoadModule("/src/components/chat/ToolActivityList.tsx"),
      server.ssrLoadModule("/src/components/chat/AssistantMessage.tsx"),
      server.ssrLoadModule("/src/lib/chat-events.ts"),
      server.ssrLoadModule("/src/components/chat/MarkdownContent.tsx"),
      server.ssrLoadModule("/src/components/settings/selection.ts"),
      server.ssrLoadModule("/src/lib/session-tree.ts"),
      server.ssrLoadModule("/src/components/sidebar/session-tree.ts"),
      server.ssrLoadModule("/src/components/settings/draft.ts"),
      server.ssrLoadModule("/src/components/SettingsView.tsx"),
      server.ssrLoadModule("/src/components/settings/tool-selection.ts"),
      server.ssrLoadModule("/src/lib/workspaces.ts"),
    ]);
});

after(async () => {
  await server?.close();
});

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

test("stopped and failed iterations render only inside the execution process", () => {
  const iterations = [
    {
      id: "iteration-1",
      iteration: 0,
      reasoning: "处理中",
      content: "部分回答",
    },
  ];

  assert.deepEqual(
    assistantMessage.iterationsOutsideExecutionProcess(
      iterations,
      iterations,
      null,
      false,
    ),
    [],
  );
  assert.deepEqual(
    assistantMessage.iterationsOutsideExecutionProcess(
      iterations,
      [],
      null,
      false,
    ),
    iterations,
  );
});

test("a completed run keeps its final answer outside the execution process", () => {
  const executionIteration = {
    id: "iteration-1",
    iteration: 0,
    reasoning: "处理中",
    content: "",
  };
  const finalAnswerIteration = {
    id: "iteration-2",
    iteration: 1,
    content: "最终答案",
  };

  assert.deepEqual(
    assistantMessage.iterationsOutsideExecutionProcess(
      [executionIteration, finalAnswerIteration],
      [executionIteration],
      finalAnswerIteration,
      false,
    ),
    [finalAnswerIteration],
  );
});

test("markdown renders inline math, display math, GFM, and literal code", () => {
  const content = [
    "Inline: $E = mc^2$",
    "",
    "$$",
    "\\sum_{i=1}^n i = \\frac{n(n+1)}{2}",
    "$$",
    "",
    "| Name | Formula |",
    "| --- | --- |",
    "| Energy | $E = mc^2$ |",
    "",
    "`$not_math$`",
  ].join("\n");
  const html = renderToStaticMarkup(
    createElement(markdownContent.StreamedMarkdown, { content }),
  );

  assert.match(html, /class="katex"/);
  assert.match(html, /class="katex-display"/);
  assert.match(html, /<table>/);
  assert.match(html, /<code>\$not_math\$<\/code>/);
});

test("invalid and unfinished math never break streamed markdown", () => {
  const invalidHtml = renderToStaticMarkup(
    createElement(markdownContent.StreamedMarkdown, {
      content: "Invalid: $\\notARealCommand{x}$",
    }),
  );
  const unfinishedHtml = renderToStaticMarkup(
    createElement(markdownContent.StreamedMarkdown, {
      content: "正在生成 $E = mc",
    }),
  );
  const untrustedHtml = renderToStaticMarkup(
    createElement(markdownContent.StreamedMarkdown, {
      content: "$\\includegraphics{https://example.com/test.png}$",
    }),
  );

  assert.match(invalidHtml, /notARealCommand/);
  assert.match(invalidHtml, /color:#cc0000/);
  assert.match(unfinishedHtml, /正在生成/);
  assert.match(unfinishedHtml, /\$E = mc/);
  assert.doesNotMatch(untrustedHtml, /<img/);
});

test("settings editor exposes context navigation and every config domain", () => {
  const html = renderToStaticMarkup(
    createElement(settingsView.SettingsView, {
      settings: {
        provider: {
          type: "openai_chat_completions",
          model: "test-model",
          base_url: "https://example.test/v1",
          api_key_configured: true,
        },
        generation: {},
        agent: {
          instructions: null,
          dynamic_context: {},
          skill_names: null,
          tool_names: null,
        },
        runtime: {
          workspace: "/tmp/project",
        },
        mcp_servers: [],
      },
      mode: "settings",
      hasRunningSessions: false,
      onCancel() {},
      async onSave(settings) {
        return settings;
      },
    }),
  );

  assert.match(html, />上下文</);
  assert.doesNotMatch(html, />Agent</);
  assert.match(html, />工具</);
  assert.match(html, />技能</);
  assert.doesNotMatch(html, />技能与工具</);
  assert.match(html, />运行环境</);
  assert.doesNotMatch(html, /<span>MCP 服务<\/span>/);
  assert.doesNotMatch(html, />高级</);
  assert.doesNotMatch(html, />Extra Body</);
  assert.doesNotMatch(html, /BumbleHive/);
  assert.match(html, /aria-haspopup="dialog"/);
  assert.match(html, /role="switch"/);
  assert.match(html, /aria-label="思考模式"/);
  assert.doesNotMatch(html, />开启思考</);
  assert.doesNotMatch(html, />关闭思考</);
  assert.match(html, /aria-label="推理强度"/);
  assert.doesNotMatch(html, /<option value="low">/);
  assert.doesNotMatch(html, />工具超时/);
  assert.doesNotMatch(html, />启用工具/);
});

test("initial setup exposes only the required model connection", () => {
  const html = renderToStaticMarkup(
    createElement(settingsView.SettingsView, {
      settings: {
        provider: {
          type: "openai_chat_completions",
          model: null,
          base_url: null,
          api_key_configured: false,
        },
        generation: {},
        agent: {
          instructions: null,
          dynamic_context: {},
          skill_names: null,
          tool_names: null,
        },
        runtime: {
          workspace: "/tmp/project",
        },
        mcp_servers: [],
      },
      mode: "setup",
      hasRunningSessions: false,
      onCancel() {},
      async onSave(settings) {
        return settings;
      },
    }),
  );

  assert.match(html, />连接模型</);
  assert.match(html, />保存并开始</);
  assert.match(html, />Base URL</);
  assert.match(html, />API Key</);
  assert.match(html, />模型</);
  assert.match(html, />所有更改已保存</);
  assert.doesNotMatch(html, />有尚未保存的更改</);
  assert.doesNotMatch(html, />所有设置</);
  assert.doesNotMatch(html, />上下文</);
  assert.doesNotMatch(html, />生成参数</);
  assert.doesNotMatch(html, />放弃更改</);
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

test("option switches preserve the automatic all-enabled mode", () => {
  const available = ["apply_patch", "github_search", "filesystem_read"];
  const afterDisable = optionSelection.setOptionsEnabled(
    null,
    ["github_search"],
    false,
    available,
  );
  assert.deepEqual(afterDisable, ["apply_patch", "filesystem_read"]);
  assert.equal(
    optionSelection.setOptionsEnabled(
      afterDisable,
      ["github_search"],
      true,
      available,
    ),
    null,
  );
  assert.equal(optionSelection.optionIsEnabled(null, "new-option"), true);
});

test("settings draft maps UI fields back to the complete config shape", () => {
  const draft = settingsDraft.settingsToDraft(
    {
      provider: {
        type: "openai_chat_completions",
        model: "test-model",
        api_key_configured: false,
      },
      generation: {},
      agent: {
        instructions: "Be concise",
        dynamic_context: { project: "bumblehive" },
        skill_names: ["review"],
        tool_names: [],
      },
      runtime: {
        workspace: "/tmp/project",
      },
      mcp_servers: [
        {
          name: "docs",
          url: "https://mcp.example.test",
          headers: { Authorization: "" },
        },
      ],
    },
    "Asia/Shanghai",
  );
  assert.equal(draft.generation.maxCompletionTokens, 16_384);
  assert.equal(draft.runtime.workspace, "/tmp/project");
  assert.equal(draft.runtime.timezone, "Asia/Shanghai");
  assert.equal(draft.runtime.contextWindowTokens, 200_000);
  assert.equal(draft.runtime.maxToolResultChars, 20_000);
  assert.equal(draft.runtime.maxIterations, 300);
  draft.generation.thinkingEnabled = false;
  draft.generation.reasoningEffort = "vendor-ultra";

  const update = settingsDraft.draftToUpdate(draft, "temporary-secret");

  assert.equal(update.provider.api_key, "temporary-secret");
  assert.deepEqual(update.agent.dynamic_context, {
    project: "bumblehive",
  });
  assert.deepEqual(update.agent.skill_names, ["review"]);
  assert.deepEqual(update.agent.tool_names, []);
  assert.deepEqual(update.generation.extra_body, {
    thinking: { type: "disabled" },
  });
  assert.equal(update.generation.reasoning_effort, null);
  assert.equal(update.generation.max_completion_tokens, 16_384);
  assert.equal(update.runtime.context_window_tokens, 200_000);
  assert.equal(update.runtime.max_tool_result_chars, 20_000);
  assert.equal(update.runtime.max_iterations, 300);
  assert.equal(update.runtime.workspace, "/tmp/project");
  assert.equal(update.runtime.timezone, "Asia/Shanghai");
  assert.deepEqual(update.mcp_servers, [
    {
      name: "docs",
      url: "https://mcp.example.test",
      headers: { Authorization: "" },
    },
  ]);
});

test("configured timezone takes priority over the detected system timezone", () => {
  const draft = settingsDraft.settingsToDraft(
    {
      provider: {
        type: "openai_chat_completions",
        model: "test-model",
        api_key_configured: false,
      },
      generation: {},
      agent: {
        dynamic_context: {},
        skill_names: null,
        tool_names: null,
      },
      runtime: {
        timezone: "Europe/Paris",
      },
      mcp_servers: [],
    },
    "Asia/Shanghai",
  );

  assert.equal(draft.runtime.timezone, "Europe/Paris");
});

test("settings draft switches disabled thinking to a custom reasoning effort", () => {
  const draft = settingsDraft.settingsToDraft({
    provider: {
      type: "openai_chat_completions",
      model: "test-model",
      api_key_configured: false,
    },
    generation: {
      reasoning_effort: null,
      extra_body: {
        top_k: 20,
        thinking: { type: "disabled" },
      },
    },
    agent: {
      dynamic_context: {},
      skill_names: null,
      tool_names: null,
    },
    runtime: {},
    mcp_servers: [],
  });

  assert.equal(draft.generation.thinkingEnabled, false);
  assert.equal(draft.generation.reasoningEffort, "");

  draft.generation.thinkingEnabled = true;
  draft.generation.reasoningEffort = "vendor-ultra";
  const update = settingsDraft.draftToUpdate(draft, "");

  assert.equal(Object.hasOwn(update.provider, "api_key"), false);
  assert.equal(update.generation.reasoning_effort, "vendor-ultra");
  assert.equal(update.generation.extra_body, null);
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


function approvalFrame(callId = "call-1", name = "write_file") {
  return {
    type: "approval_request",
    approval_id: `approval-${callId}`,
    session_id: "session-1",
    call_id: callId,
    name,
    reason: name,
    workspace: "/workspace",
    paths: ["/outside.txt"],
    outside_paths: ["/outside.txt"],
    arguments: { path: "/outside.txt", content: "hello" },
  };
}

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

test("question cards support choices and free-text-only questions without automatic submission", async () => {
  const { QuestionCard } = await server.ssrLoadModule("/src/components/QuestionCard.tsx");
  const question = {
    session_id: "one", task_id: "q1", question: "选择数据库",
    options: ["PostgreSQL（推荐）", "MySQL"],
  };
  const render = (item, disconnected = false) => renderToStaticMarkup(createElement(QuestionCard, {
    question: item, disconnected, onSkip() { assert.fail("render must not skip"); }, onAnswer() { assert.fail("render must not submit"); },
  }));
  const choices = render(question);
  assert.match(choices, /可选答案/);
  assert.match(choices, /PostgreSQL（推荐）/);
  assert.match(choices, /自由填写回答/);
  assert.match(choices, /class="question-send" disabled/);
  assert.doesNotMatch(choices, /aria-pressed="true"/);
  const free = render({ ...question, options: [] });
  assert.doesNotMatch(free, /可选答案|question-number/);
  assert.match(free, /请填写你的回答/);
  assert.match(render(question, true), /重连后可继续回答/);
  assert.match(render({ ...question, error: "answer rejected" }), /role="alert">answer rejected/);
  assert.match(choices, /aria-label="跳过此问题"/);
  assert.doesNotMatch(choices, /收起|展开/);
});

test("question frames restore cards and scope answers and errors to their own session", async () => {
  const { applyQuestionFrame } = await server.ssrLoadModule("/src/lib/questions.ts");
  const q = { task_id: "q", question: "Database?", options: [] };
  let items = applyQuestionFrame([], "one", { type: "question_request", session_id: "one", ...q });
  items = applyQuestionFrame(items, "two", { type: "question_request", session_id: "two", ...q });
  items = items.map((item) => ({ ...item, submitting: true }));
  items = applyQuestionFrame(items, "one", {
    type: "error", scope: "input", task_id: "q", message: "try again",
  });
  assert.equal(items[0].submitting, false);
  assert.equal(items[0].error, "try again");
  assert.equal(items[1].submitting, true);
  items = applyQuestionFrame(items, "one", {
    type: "question_closed", task_id: "q",
  });
  assert.equal(items.length, 1);
  assert.equal(items[0].session_id, "two");
  items = applyQuestionFrame(items, "two", { type: "question_closed", task_id: "q" });
  assert.deepEqual(items, []);
  items = applyQuestionFrame(items, "two", {
    type: "ready", questions: [
      { ...q, task_id: "pending" },
    ],
  });
  assert.deepEqual(items.map((item) => item.task_id), ["pending"]);
  assert.equal(items[0].submitting, undefined);
  items = applyQuestionFrame(items, "two", { type: "question_closed", task_id: "pending" });
  assert.deepEqual(items, []);
  items = applyQuestionFrame(items, "two", { type: "ready", questions: [] });
  assert.deepEqual(items, []);
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

test("approval card displays actual operation, decision controls, and submitting state", () => {
  const props = { count: 2, isStopping: false, onDecide() {}, onStop() {} };
  const html = renderToStaticMarkup(createElement(approvalCard.ApprovalCard, {
    ...props,
    approval: { ...approvalFrame(), submitting: false, sourceSessionId: "session-1" },
  }));
  for (const text of ["/outside.txt", "/workspace", "hello", "拒绝", "允许一次", "停止任务", "2 项待确认"]) assert.ok(html.includes(text));
  const shellHtml = renderToStaticMarkup(createElement(approvalCard.ApprovalCard, {
    ...props,
    approval: { ...approvalFrame("shell", "exec"), command: "echo <hello> > /tmp/outside", working_dir: "/workspace", submitting: true },
  }));
  assert.match(shellHtml, /echo &lt;hello&gt; &gt; \/tmp\/outside/);
  assert.match(shellHtml, /处理中/);
  assert.match(shellHtml, /disabled=""[^>]*>允许一次/);
});


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

test("composer places approval mode after workspace and disables changes during a run", async () => {
  const { Composer } = await server.ssrLoadModule("/src/components/Composer.tsx");
  const props = {
    value: "", model: "model", models: [], workspace: "demo", disabled: false,
    isStreaming: false, isStopping: false, modelSwitchDisabled: false,
    approvalMode: "request", onSelectApprovalMode() {}, onChange() {},
    onSubmit() {}, onStop() {}, onAddWorkspace() {}, async onSelectModel() {},
  };
  const html = renderToStaticMarkup(createElement(Composer, props));
  assert.ok(html.indexOf(">demo</span>") < html.indexOf("审批模式：请求批准"));
  const running = renderToStaticMarkup(createElement(Composer, {
    ...props, approvalMode: "full_access", isStreaming: true,
  }));
  assert.match(running, /aria-label="审批模式：完全访问"[^>]*disabled=""/);
});

test("chat socket sends the selected approval mode with each task", async () => {
  const { ChatSocket } = await server.ssrLoadModule("/src/api/chat-socket.ts");
  const previous = globalThis.WebSocket;
  const sent = [];
  globalThis.WebSocket = class {
    static OPEN = 1;
    readyState = 1;
    constructor() {
      queueMicrotask(() => this.onmessage({ data: JSON.stringify({ type: "ready", session_id: "session" }) }));
    }
    send(message) { sent.push(JSON.parse(message)); }
    close() {}
  };
  const socket = new ChatSocket("session", { onFrame() {}, onDisconnect() {} });
  try {
    await socket.connect();
    socket.send("one", "/workspace", "full_access");
    socket.send("two", "/workspace", "request");
    assert.deepEqual(sent.map((message) => message.approval_mode), ["full_access", "request"]);
    assert.equal(sent[0].config.runtime.workspace, "/workspace");
  } finally {
    socket.close();
    globalThis.WebSocket = previous;
  }
});

test("composer renders multiple pending rows with independent steer and delete controls", async () => {
  const { Composer } = await server.ssrLoadModule("/src/components/Composer.tsx");
  const html = renderToStaticMarkup(createElement(Composer, {
    value: "第三条", model: "model", models: [], workspace: "demo", disabled: false,
    isStreaming: true, isStopping: false, modelSwitchDisabled: true,
    approvalMode: "request", onSelectApprovalMode() {}, onChange() {},
    onSubmit() {}, onStop() {}, onAddWorkspace() {}, async onSelectModel() {},
    pendingMessages: [{ message_id: "B", content: "只修改后端" }, { message_id: "C", content: "保留原样式", submitting: true }],
    onPendingAction() {},
  }));
  assert.ok(html.indexOf("只修改后端") < html.indexOf("保留原样式"));
  assert.equal((html.match(/class="pending-message"/g) ?? []).length, 2);
  assert.match(html, /删除待发送消息：只修改后端/);
  assert.match(html, /引导/);
  assert.match(html, /排队发送/);
  assert.doesNotMatch(html, /<textarea[^>]*disabled/);
});

test("chat socket processes ready snapshot before events and sends message IDs and pending actions", async () => {
  const { ChatSocket } = await server.ssrLoadModule("/src/api/chat-socket.ts");
  const previous = globalThis.WebSocket;
  const frames = [], sent = [];
  let instance, release;
  const hydration = new Promise((resolve) => { release = resolve; });
  globalThis.WebSocket = class {
    static OPEN = 1;
    readyState = 1;
    constructor() {
      instance = this;
      queueMicrotask(() => {
        this.onmessage({ data: JSON.stringify({ type: "ready", session_id: "one", running: true, pending: [{ message_id: "B", content: "queued" }] }) });
        this.onmessage({ data: JSON.stringify({ type: "event", session_id: "one", kind: "model.stream.content_delta", payload: { delta: "next" } }) });
      });
    }
    send(text) { sent.push(JSON.parse(text)); }
    close() {}
  };
  const socket = new ChatSocket("one", {
    async onFrame(frame) {
      if (frame.type === "ready") await hydration;
      frames.push(frame);
    },
    onDisconnect() {},
  });
  try {
    const connected = socket.connect();
    await new Promise((resolve) => setTimeout(resolve, 0));
    assert.deepEqual(frames, []);
    release();
    await connected;
    await socket.whenSynced();
    assert.deepEqual(frames.map((f) => f.type), ["ready", "event"]);
    socket.send("new", "/workspace", "request", "C");
    socket.updatePending("steer", "B");
    socket.updatePending("remove_pending", "C");
    socket.answerQuestion("q-1", "PostgreSQL（推荐）：保留完整文本");
    socket.answerQuestion("q-2");
    assert.equal(sent[0].message_id, "C");
    assert.deepEqual(sent.slice(1), [
      { type: "steer", message_id: "B" }, { type: "remove_pending", message_id: "C" },
      { type: "question_answer", task_id: "q-1", answer: "PostgreSQL（推荐）：保留完整文本" },
      { type: "question_skip", task_id: "q-2" },
    ]);
    assert.equal(instance.readyState, 1);
  } finally {
    socket.close();
    globalThis.WebSocket = previous;
  }
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

test("simultaneous connect calls share one handshake until the ready snapshot is restored", async () => {
  const { ChatSocket } = await server.ssrLoadModule("/src/api/chat-socket.ts");
  const previous = globalThis.WebSocket;
  let instance, count = 0;
  globalThis.WebSocket = class {
    static OPEN = 1;
    readyState = 1;
    constructor() { instance = this; count++; }
    close() {}
  };
  const socket = new ChatSocket("one", { onFrame() {}, onDisconnect() {} });
  try {
    const first = socket.connect();
    const second = socket.connect();
    assert.equal(first, second);
    assert.equal(count, 1);
    let resolved = false;
    void second.then(() => { resolved = true; });
    await Promise.resolve();
    assert.equal(resolved, false);
    instance.onmessage({ data: JSON.stringify({ type: "ready", session_id: "one" }) });
    await first;
    assert.equal(resolved, true);
  } finally {
    socket.close();
    globalThis.WebSocket = previous;
  }
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

test("running background children can be deleted while foreground branches remain protected", async () => {
  const { SessionBranch } = await server.ssrLoadModule("/src/components/sidebar/SessionBranch.tsx");
  const render = (blocked) => renderToStaticMarkup(createElement(SessionBranch, {
    session: { id: "child", title: "Child", children: [] }, depth: 1,
    activeSessionId: "child", expandedSessionIds: new Set(), runningSessionIds: new Set(["child"]),
    blockingSessionIds: blocked, searching: false, sessionSelectionDisabled: false,
    onToggle() {}, onSelect() {}, onDelete() {},
  }));
  const background = render(new Set());
  const foreground = render(new Set(["child"]));
  assert.doesNotMatch(background, /class="session-delete"[^>]*disabled/);
  assert.match(foreground, /class="session-delete"[^>]*disabled/);
});
