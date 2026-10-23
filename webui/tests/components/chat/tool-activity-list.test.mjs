import assert from "node:assert/strict";
import { before, test } from "node:test";
import { server } from "../../helpers/vite.mjs";

let toolActivityList;

before(async () => {
  toolActivityList = await server.ssrLoadModule("/src/components/chat/ToolActivityList.tsx");
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
