import assert from "node:assert/strict";
import { test } from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { server } from "../helpers/vite.mjs";

test("approval replaces composer input and toolbar while keeping questions and queued messages", async () => {
  const { Composer } = await server.ssrLoadModule("/src/components/Composer.tsx");
  const props = {
    value: "保留的草稿", model: "model", models: [], workspace: "demo", disabled: false,
    isStreaming: true, isStopping: false, modelSwitchDisabled: true,
    approvalMode: "request", onSelectApprovalMode() {}, onChange() {},
    onSubmit() {}, onStop() {}, onAddWorkspace() {}, async onSelectModel() {},
    questionSlot: createElement("div", null, "待回答的问题"),
    pendingMessages: [{ message_id: "queued", content: "待发送的消息", submitting: false }],
  };
  const html = renderToStaticMarkup(createElement(Composer, {
    ...props, approvalSlot: createElement("section", null, "审批卡片"),
  }));
  assert.match(html, /composer-approving/);
  for (const label of ["审批卡片", "待回答的问题", "待发送的消息"]) assert.ok(html.includes(label));
  assert.doesNotMatch(html, /输入任务|composer-toolbar|保留的草稿/);
  const normal = renderToStaticMarkup(createElement(Composer, props));
  assert.match(normal, /输入任务/);
  assert.match(normal, /保留的草稿/);
  assert.match(normal, /composer-toolbar/);
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
