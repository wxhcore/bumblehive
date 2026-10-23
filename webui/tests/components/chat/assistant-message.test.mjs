import assert from "node:assert/strict";
import { before, test } from "node:test";
import { server } from "../../helpers/vite.mjs";

let assistantMessage;

before(async () => {
  assistantMessage = await server.ssrLoadModule("/src/components/chat/AssistantMessage.tsx");
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
