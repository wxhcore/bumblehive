import assert from "node:assert/strict";
import { test } from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { server } from "../helpers/vite.mjs";

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
