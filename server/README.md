# Bumblehive Server

FastAPI adapter for the Bumblehive Python SDK.

## Development

From the repository root:

```bash
conda activate bumblehive_env
pnpm run setup
pnpm run dev:server
```

See the root README for the Node.js and pnpm prerequisites. The root launcher sets the cross-platform `PYTHONPATH` automatically. Use `pnpm run dev` to start the Server and WebUI together.

The server listens on `127.0.0.1:18421` by default and reads configuration from
`~/.bumblehive/config.json`.

Environment overrides:

```text
BUMBLEHIVE_CONFIG=/path/to/config.json
BUMBLEHIVE_HOST=127.0.0.1
BUMBLEHIVE_PORT=18421
BUMBLEHIVE_ALLOWED_ORIGINS=http://127.0.0.1:1420,tauri://localhost
```

## API

```text
GET    /api/v1/health
GET    /api/v1/settings
PUT    /api/v1/settings
POST   /api/v1/sessions
GET    /api/v1/sessions
GET    /api/v1/sessions/{session_id}
DELETE /api/v1/sessions/{session_id}
WS     /ws/v1/chat/{session_id}
```

### Chat input

Send `{"type":"message","message_id":"unique-id","content":"..."}` to start a
turn or queue a follow-up. Follow-ups run one at a time in submission order.
Use `{"type":"steer","message_id":"..."}` to send a queued message into the
current turn, or `{"type":"remove_pending","message_id":"..."}` to remove it.
The server acknowledges each change with `message_status`: `queued`, `started`,
`steered`, or `removed`.

Each session owns its run, pending messages and approvals. Closing the WebSocket
only disconnects that subscriber. On reconnect, `ready` returns the current run,
pending messages and approvals; load saved conversation history through the
session API. Stream events from the disconnected interval are not replayed.
Cancellation and errors pause follow-ups; send a pending message explicitly to
resume. Steering that the SDK has not consumed is restored with its original
message ID and queue order. Its `queued` receipt includes a zero-based `position`
so clients can reinsert the card at the correct place. Consumed steering is not
requeued. Pending messages survive a connection loss, but are held in memory and
do not survive a server restart.

### Ask user

The application registers `ask_user(question, options?)` without requiring tool
approval. It asks one question, with optional suggested answers and an always
available free-text input above the composer. Its `task_id` is the originating
tool call ID, shared by the card, submissions, and results.

During the first 60 seconds, an answer returns
`{"task_id":"...","status":"answered","answer":"..."}` and skipping returns
`{"task_id":"...","status":"skipped"}`. Otherwise the tool returns
`{"task_id":"...","status":"pending"}` and keeps the question answerable for
up to 120 more seconds. A background answer delivers `answered`; skipping,
closing the card, or reaching the deadline delivers `skipped`. Background results
use the session notification queue: steering while running, a new turn while
naturally idle, or queued until resume after a stop or error. They do not append
a second tool response for the original call.

The server sends `question_request`. Submit
`{"type":"question_answer","task_id":"...","answer":"..."}` to answer, or
`{"type":"question_skip","task_id":"..."}` to skip. The × and Skip buttons
both end the question. On completion, the server removes the question and sends
`question_closed`; the frontend removes its card. The first answer, skip, or
expiration wins. Input errors include `task_id` so the corresponding card can be
resubmitted. Ended questions are not retained or replayed.

Only unresolved questions appear in `ready.questions`. Switching sessions or
losing the connection does not reset the server deadline. Stopping during the
initial wait leaves the card answerable without starting a background deadline;
a later answer follows the normal user-input path. Stopping after `pending`
leaves the background deadline running, but automatic results do not resume the
stopped Agent. Closing or deleting the server session cancels its question
waiters. Questions do not survive a server restart. Sub-agents do not receive
this tool.

Backend callers can deliver input to a running turn or start one while idle:

```python
controller = service.get_session_controller(session_id)
await controller.submit(request, steer=True)
```

### Sub-agents

The server's read-only `sub_agent(title, task)` runs in the background and returns
`{"status":"pending","task_id":"..."}` after startup. The task ID is the
originating tool call ID; success and failure reports include that same ID.
The final report or failure is delivered automatically to the parent: through
steering while running, or a new turn when naturally idle. After a stop or error,
reports stay queued until the user resumes. Background work survives disconnects
and parent-turn cancellation; deleting its session cancels it.

The parent's `ready.running_subagents` lists active background children for
reconnection. Child events retain their own session IDs. Task ownership and
pending reports are in memory; conversation history is saved as usual.

### Background result messages

The server wraps Ask User and sub-agent background results in the same
`user` message format, using the original tool call ID:

```text
[Background tool result]
Task ID: call_123

Tool return content
```

Strings are included as-is; structured results are serialized as JSON. Each
tool defines its own result content. This is a later conversation input, not a
second tool response for the original call.

## Desktop sidecar

Build the standalone binary from the repository root with the Python build
environment activated:

```bash
pnpm run build:sidecar
```

The script writes a standalone directory to
`desktop/src-tauri/sidecar/bumblehive-server/`. Tauri bundles that directory,
starts its executable when the desktop application opens, and stops it when
the application exits.
