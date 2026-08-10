import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createServer } from "vite";

let server;
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
          extra_read_roots: [],
          extra_write_roots: [],
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
          extra_read_roots: [],
          extra_write_roots: [],
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

test("runtime settings expose the opt-in shell path restriction", () => {
  const renderRuntimeSettings = (restrictExecPaths) =>
    renderToStaticMarkup(
      createElement(settingsView.SettingsView, {
        settings: {
          provider: {
            type: "openai_chat_completions",
            model: "test-model",
            api_key_configured: true,
          },
          generation: {},
          agent: {},
          runtime: { restrict_exec_paths: restrictExecPaths },
          mcp_servers: [],
        },
        mode: "settings",
        focusWorkspace: true,
        hasRunningSessions: false,
        onCancel() {},
        async onSave(settings) {
          return settings;
        },
      }),
    );

  const disabledHtml = renderRuntimeSettings(false);
  const enabledHtml = renderRuntimeSettings(true);

  assert.match(disabledHtml, /Shell 路径限制/);
  assert.match(
    disabledHtml,
    /class="setting-row setting-row-inline-control"/,
  );
  assert.match(disabledHtml, /aria-label="Shell 路径限制"/);
  assert.doesNotMatch(disabledHtml, /aria-label="Shell 路径限制" checked/);
  assert.doesNotMatch(disabledHtml, /额外只读目录/);
  assert.doesNotMatch(disabledHtml, /额外可写目录/);

  assert.match(enabledHtml, /aria-label="Shell 路径限制" checked/);
  assert.match(enabledHtml, /额外只读目录/);
  assert.match(enabledHtml, /额外可写目录/);
  assert.ok(
    enabledHtml.indexOf("Shell 路径限制") <
      enabledHtml.indexOf("额外只读目录"),
  );
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
        extra_read_roots: ["/tmp/read"],
        extra_write_roots: [],
        restrict_exec_paths: true,
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
  assert.equal(draft.runtime.timezone, "Asia/Shanghai");
  assert.equal(draft.runtime.contextWindowTokens, 200_000);
  assert.equal(draft.runtime.maxToolResultChars, 20_000);
  assert.equal(draft.runtime.maxIterations, 300);
  assert.equal(draft.runtime.restrictExecPaths, true);
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
  assert.equal(update.runtime.timezone, "Asia/Shanghai");
  assert.deepEqual(update.runtime.extra_read_roots, ["/tmp/read"]);
  assert.equal(update.runtime.restrict_exec_paths, true);
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
        extra_read_roots: [],
        extra_write_roots: [],
      },
      mcp_servers: [],
    },
    "Asia/Shanghai",
  );

  assert.equal(draft.runtime.timezone, "Europe/Paris");
  assert.equal(draft.runtime.restrictExecPaths, false);
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
    runtime: {
      extra_read_roots: [],
      extra_write_roots: [],
    },
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
