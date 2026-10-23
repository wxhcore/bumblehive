import assert from "node:assert/strict";
import { test } from "node:test";
import { server } from "../helpers/vite.mjs";

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
