import assert from "node:assert/strict";
import { before, test } from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { server } from "../helpers/vite.mjs";
import { approvalFrame } from "../fixtures/approval.mjs";

let approvalCard;

before(async () => {
  approvalCard = await server.ssrLoadModule("/src/components/ApprovalCard.tsx");
});

test("approval card displays actual operation, decision controls, and submitting state", () => {
  const props = { count: 2, isStopping: false, onDecide() {} };
  const html = renderToStaticMarkup(createElement(approvalCard.ApprovalCard, {
    ...props,
    approval: { ...approvalFrame(), submitting: false, sourceSessionId: "session-1" },
  }));
  for (const text of ["/outside.txt", "hello", "拒绝", "允许一次", "2 项待确认"]) assert.ok(html.includes(text));
  assert.doesNotMatch(html, /操作详情|停止任务|工作目录：|<details/);
  const shellHtml = renderToStaticMarkup(createElement(approvalCard.ApprovalCard, {
    ...props,
    approval: { ...approvalFrame("shell", "exec"), command: "echo <hello> > /tmp/outside", working_dir: "/workspace", submitting: true },
  }));
  assert.match(shellHtml, /echo &lt;hello&gt; &gt; \/tmp\/outside/);
  assert.doesNotMatch(shellHtml, /操作详情|停止任务|工作目录：|<details/);
  assert.equal((shellHtml.match(/echo &lt;hello&gt; &gt; \/tmp\/outside/g) ?? []).length, 1);
  assert.match(shellHtml, /处理中/);
  assert.match(shellHtml, /disabled=""[^>]*>允许一次/);
});

test("exec approval uses justification and falls back for missing or blank explanations", () => {
  for (const justification of ["  是否允许安装依赖？  ", undefined, "   ", 123]) {
    const html = renderToStaticMarkup(createElement(approvalCard.ApprovalCard, {
      count: 1, isStopping: false, onDecide() {},
      approval: {
        ...approvalFrame("shell", "exec"), submitting: false,
        command: "npm install", arguments: { command: "npm install", justification },
      },
    }));
    const prompt = html.match(/class="approval-prompt">([^<]*)<\/p>/)?.[1];
    assert.equal(prompt, typeof justification === "string" && justification.trim()
      ? justification.trim() : "是否允许执行以下命令？");
    assert.match(html, /aria-expanded="true"/);
  }
});

test("disconnected approvals disable decisions", () => {
  const html = renderToStaticMarkup(createElement(approvalCard.ApprovalCard, {
    count: 1, isStopping: false, disconnected: true, onDecide() {},
    approval: { ...approvalFrame(), submitting: false },
  }));
  assert.match(html, /连接已中断，等待重连/);
  for (const label of ["拒绝", "允许一次"]) {
    assert.match(html, new RegExp(`disabled=""[^>]*>${label}`));
  }
});
