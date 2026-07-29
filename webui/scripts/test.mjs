import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createServer } from "vite";

let server;
let assistantMessage;
let chatEvents;
let markdownContent;
let sessionTree;
let sidebarTree;

before(async () => {
  server = await createServer({
    appType: "custom",
    logLevel: "silent",
    server: { middlewareMode: true },
  });
  [assistantMessage, chatEvents, markdownContent, sessionTree, sidebarTree] =
    await Promise.all([
      server.ssrLoadModule("/src/components/chat/AssistantMessage.tsx"),
      server.ssrLoadModule("/src/lib/chat-events.ts"),
      server.ssrLoadModule("/src/components/chat/MarkdownContent.tsx"),
      server.ssrLoadModule("/src/lib/session-tree.ts"),
      server.ssrLoadModule("/src/components/sidebar/session-tree.ts"),
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
