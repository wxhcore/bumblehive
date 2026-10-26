import assert from "node:assert/strict";
import { test } from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { server } from "../../helpers/vite.mjs";

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

test("parent counts and Bee children keep separate select and expand controls", async () => {
  const { SessionBranch } = await server.ssrLoadModule("/src/components/sidebar/SessionBranch.tsx");
  const props = {
    session: { id: "parent", title: "主会话", children: [{ id: "child", title: "代码分析 Bee", children: [] }] },
    depth: 0, activeSessionId: "child", expandedSessionIds: new Set(["parent"]),
    runningSessionIds: new Set(), blockingSessionIds: new Set(), searching: false,
    sessionSelectionDisabled: false, onToggle() {}, onSelect() {}, onDelete() {},
  };
  const html = renderToStaticMarkup(createElement(SessionBranch, props));
  assert.match(html, /aria-label="折叠主会话的 1 个 Bee 会话" aria-expanded="true"/);
  assert.match(html, /session-bee-mark/);
  assert.match(html, /bumblehive-bee.png/);
  assert.match(html, /conversation active[^>]*>代码分析 Bee/);
  const collapsed = renderToStaticMarkup(createElement(SessionBranch, { ...props, expandedSessionIds: new Set() }));
  assert.doesNotMatch(collapsed, /代码分析 Bee/);
  assert.match(collapsed, /展开主会话的 1 个 Bee 会话/);
});
