import assert from "node:assert/strict";
import { test } from "node:test";
import { server } from "../helpers/vite.mjs";

test("chat socket sends the selected approval mode with each task", async () => {
  const { ChatSocket } = await server.ssrLoadModule("/src/api/chat-socket.ts");
  const previous = globalThis.WebSocket;
  const sent = [];
  globalThis.WebSocket = class {
    static OPEN = 1;
    readyState = 1;
    constructor() {
      queueMicrotask(() => this.onmessage({ data: JSON.stringify({ type: "ready", session_id: "session" }) }));
    }
    send(message) { sent.push(JSON.parse(message)); }
    close() {}
  };
  const socket = new ChatSocket("session", { onFrame() {}, onDisconnect() {} });
  try {
    await socket.connect();
    socket.send("one", "/workspace", "full_access");
    socket.send("two", "/workspace", "request");
    assert.deepEqual(sent.map((message) => message.approval_mode), ["full_access", "request"]);
    assert.equal(sent[0].config.runtime.workspace, "/workspace");
  } finally {
    socket.close();
    globalThis.WebSocket = previous;
  }
});

test("chat socket processes ready snapshot before events and sends message IDs and pending actions", async () => {
  const { ChatSocket } = await server.ssrLoadModule("/src/api/chat-socket.ts");
  const previous = globalThis.WebSocket;
  const frames = [], sent = [];
  let instance, release;
  const hydration = new Promise((resolve) => { release = resolve; });
  globalThis.WebSocket = class {
    static OPEN = 1;
    readyState = 1;
    constructor() {
      instance = this;
      queueMicrotask(() => {
        this.onmessage({ data: JSON.stringify({ type: "ready", session_id: "one", running: true, pending: [{ message_id: "B", content: "queued" }] }) });
        this.onmessage({ data: JSON.stringify({ type: "event", session_id: "one", kind: "model.stream.content_delta", payload: { delta: "next" } }) });
      });
    }
    send(text) { sent.push(JSON.parse(text)); }
    close() {}
  };
  const socket = new ChatSocket("one", {
    async onFrame(frame) {
      if (frame.type === "ready") await hydration;
      frames.push(frame);
    },
    onDisconnect() {},
  });
  try {
    const connected = socket.connect();
    await new Promise((resolve) => setTimeout(resolve, 0));
    assert.deepEqual(frames, []);
    release();
    await connected;
    await socket.whenSynced();
    assert.deepEqual(frames.map((f) => f.type), ["ready", "event"]);
    socket.send("new", "/workspace", "request", "C");
    socket.updatePending("steer", "B");
    socket.updatePending("remove_pending", "C");
    socket.answerQuestion("q-1", "PostgreSQL（推荐）：保留完整文本");
    socket.answerQuestion("q-2");
    assert.equal(sent[0].message_id, "C");
    assert.deepEqual(sent.slice(1), [
      { type: "steer", message_id: "B" }, { type: "remove_pending", message_id: "C" },
      { type: "question_answer", task_id: "q-1", answer: "PostgreSQL（推荐）：保留完整文本" },
      { type: "question_skip", task_id: "q-2" },
    ]);
    assert.equal(instance.readyState, 1);
  } finally {
    socket.close();
    globalThis.WebSocket = previous;
  }
});

test("simultaneous connect calls share one handshake until the ready snapshot is restored", async () => {
  const { ChatSocket } = await server.ssrLoadModule("/src/api/chat-socket.ts");
  const previous = globalThis.WebSocket;
  let instance, count = 0;
  globalThis.WebSocket = class {
    static OPEN = 1;
    readyState = 1;
    constructor() { instance = this; count++; }
    close() {}
  };
  const socket = new ChatSocket("one", { onFrame() {}, onDisconnect() {} });
  try {
    const first = socket.connect();
    const second = socket.connect();
    assert.equal(first, second);
    assert.equal(count, 1);
    let resolved = false;
    void second.then(() => { resolved = true; });
    await Promise.resolve();
    assert.equal(resolved, false);
    instance.onmessage({ data: JSON.stringify({ type: "ready", session_id: "one" }) });
    await first;
    assert.equal(resolved, true);
  } finally {
    socket.close();
    globalThis.WebSocket = previous;
  }
});
