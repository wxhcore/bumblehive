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
