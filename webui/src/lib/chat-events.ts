import {
  detailFromStoredToolResult,
  normalizeToolActivityOutcome,
  parseToolActivityDetail,
  toolResultError,
} from "../tool-details";
import type {
  AgentEventFrame,
  AssistantIteration,
  ChatFrame,
  StoredMessage,
  ToolActivity,
  UiMessage,
} from "../types/api";

const STREAM_TEXT_EVENT_KINDS = new Set([
  "model.stream.content_delta",
  "model.stream.reasoning_delta",
  "model.stream.refusal_delta",
]);

export function createMessageId(): string {
  return crypto.randomUUID();
}

export function frameSessionId(frame: ChatFrame, fallback: string): string {
  return "session_id" in frame &&
    typeof frame.session_id === "string" &&
    frame.session_id
    ? frame.session_id
    : fallback;
}

function messageContent(content: unknown): string {
  if (typeof content === "string") return content;
  if (content === null || content === undefined) return "";
  try {
    return JSON.stringify(content, null, 2);
  } catch {
    return String(content);
  }
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null
    ? (value as Record<string, unknown>)
    : null;
}

function parseArguments(value: unknown): unknown {
  if (typeof value !== "string") return value;
  try {
    return JSON.parse(value) as unknown;
  } catch {
    return value;
  }
}

function storedToolCalls(value: unknown, messageIndex: number): ToolActivity[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((rawCall, toolIndex) => {
    const call = asRecord(rawCall);
    if (!call) return [];
    const fn = asRecord(call.function);
    if (!fn) return [];
    const name = fn.name;
    if (typeof name !== "string" || !name) return [];
    return [
      {
        id:
          typeof call.id === "string" && call.id
            ? call.id
            : `history-tool-${messageIndex}-${toolIndex}`,
        name,
        arguments: parseArguments(fn.arguments),
        status: "running",
      } satisfies ToolActivity,
    ];
  });
}

export function historyMessages(messages: StoredMessage[]): UiMessage[] {
  const result: UiMessage[] = [];
  const toolsByCallId = new Map<string, ToolActivity>();

  messages.forEach((message, index) => {
    if (message.role === "user") {
      result.push({
        id: `history-${index}`,
        role: "user",
        content: messageContent(message.content),
      });
      return;
    }

    if (message.role === "assistant") {
      const content = messageContent(message.content);
      const reasoning = messageContent(message.reasoning_content);
      const tools = storedToolCalls(message.tool_calls, index);
      const uiMetadata = asRecord(message._bumblehive_ui);
      const durationSeconds =
        typeof uiMetadata?.duration_s === "number" &&
        Number.isFinite(uiMetadata.duration_s)
          ? uiMetadata.duration_s
          : undefined;
      if (!content && !reasoning && !tools.length) return;
      tools.forEach((tool) => toolsByCallId.set(tool.id, tool));
      const modelIteration: AssistantIteration = {
        id: `history-iteration-${index}`,
        iteration: null,
        content,
        reasoning: reasoning || undefined,
        tools: tools.length ? tools : undefined,
      };
      const previous = result.at(-1);
      if (previous?.role === "assistant") {
        previous.iterations = [...(previous.iterations ?? []), modelIteration];
        if (durationSeconds !== undefined) {
          previous.durationSeconds = durationSeconds;
        }
      } else {
        result.push({
          id: `history-${index}`,
          role: "assistant",
          content: "",
          iterations: [modelIteration],
          durationSeconds,
        });
      }
      return;
    }

    if (message.role === "tool") {
      const callId =
        typeof message.tool_call_id === "string" ? message.tool_call_id : "";
      const tool = callId ? toolsByCallId.get(callId) : undefined;
      if (tool) {
        const errorMessage = toolResultError(message.content);
        tool.status = errorMessage ? "error" : "completed";
        tool.errorMessage = errorMessage || undefined;
        tool.detail = detailFromStoredToolResult(tool.name, message.content);
        Object.assign(tool, normalizeToolActivityOutcome(tool));
      }
    }
  });

  return result;
}

function startedTool(payload: Record<string, unknown>): ToolActivity | null {
  const call = asRecord(payload.tool_call);
  if (!call) return null;
  const name = typeof call.name === "string" ? call.name : "工具";
  return {
    id:
      typeof call.call_id === "string" && call.call_id
        ? call.call_id
        : createMessageId(),
    name,
    arguments: call.arguments,
    status: "running",
  };
}

function finishedTool(payload: Record<string, unknown>): ToolActivity | null {
  const result = asRecord(payload.tool_result);
  if (!result) return null;
  const error = asRecord(payload.error);
  const name = typeof result.name === "string" ? result.name : "工具";
  return {
    id:
      typeof result.tool_call_id === "string" && result.tool_call_id
        ? result.tool_call_id
        : createMessageId(),
    name,
    status: payload.ok === true ? "completed" : "error",
    durationSeconds:
      typeof payload.duration_s === "number" ? payload.duration_s : undefined,
    errorMessage:
      typeof error?.message === "string" ? error.message : undefined,
    detail: parseToolActivityDetail(result.detail),
  };
}

function startTool(
  tools: ToolActivity[] | undefined,
  started: ToolActivity,
): ToolActivity[] {
  const current = [...(tools ?? [])];
  const index = current.findIndex(
    (tool) =>
      tool.id === started.id ||
      (tool.status === "preparing" && tool.name === started.name),
  );
  if (index === -1) return [...current, started];
  current[index] = { ...current[index], ...started };
  return current;
}

function prepareTool(
  tools: ToolActivity[] | undefined,
  payload: Record<string, unknown>,
  iteration: number | null,
): ToolActivity[] {
  const current = [...(tools ?? [])];
  const streamIndex =
    typeof payload.index === "number" ? payload.index : 0;
  const callId =
    typeof payload.call_id === "string" && payload.call_id
      ? payload.call_id
      : "";
  const index = current.findIndex(
    (tool) =>
      tool.streamIndex === streamIndex || Boolean(callId && tool.id === callId),
  );
  const existing = index >= 0 ? current[index] : undefined;
  const streamedArguments =
    (existing?.streamedArguments ?? "") +
    (typeof payload.arguments_delta === "string"
      ? payload.arguments_delta
      : "");
  const name =
    typeof payload.name === "string" && payload.name
      ? payload.name
      : existing?.name || "工具";
  const prepared: ToolActivity = {
    ...existing,
    id:
      callId ||
      existing?.id ||
      `stream-tool-${iteration ?? "unknown"}-${streamIndex}`,
    name,
    arguments: parseArguments(streamedArguments),
    streamedArguments,
    streamIndex,
    status: "preparing",
  };

  if (index < 0) return [...current, prepared];
  current[index] = prepared;
  return current;
}

function finishTool(
  tools: ToolActivity[] | undefined,
  finished: ToolActivity,
): ToolActivity[] {
  const current = [...(tools ?? [])];
  let index = current.findIndex((tool) => tool.id === finished.id);
  if (index < 0) {
    for (let candidate = current.length - 1; candidate >= 0; candidate -= 1) {
      const tool = current[candidate];
      if (
        (tool.status === "running" || tool.status === "preparing") &&
        tool.name === finished.name
      ) {
        index = candidate;
        break;
      }
    }
  }
  if (index === -1) {
    return [...current, normalizeToolActivityOutcome(finished)];
  }
  current[index] = normalizeToolActivityOutcome({
    ...current[index],
    ...finished,
  });
  return current;
}

type IterationUpdateKind = "model" | "tool";

function updateAssistantIteration(
  iterations: AssistantIteration[] | undefined,
  iteration: number | null,
  kind: IterationUpdateKind,
  update: (current: AssistantIteration) => AssistantIteration,
): AssistantIteration[] {
  const current = [...(iterations ?? [])];
  let index =
    iteration === null
      ? current.length - 1
      : current.findIndex((item) => item.iteration === iteration);

  if (
    index < 0 ||
    (iteration === null &&
      kind === "model" &&
      Boolean(current[index]?.tools?.length))
  ) {
    current.push({
      id: createMessageId(),
      iteration,
      content: "",
    });
    index = current.length - 1;
  }

  current[index] = update(current[index]);
  return current;
}

function finishIterationTool(
  iterations: AssistantIteration[] | undefined,
  iteration: number | null,
  finished: ToolActivity,
): AssistantIteration[] {
  const current = [...(iterations ?? [])];
  let ownerIndex = current.findIndex((item) =>
    item.tools?.some((tool) => tool.id === finished.id),
  );
  if (ownerIndex < 0) {
    for (
      let candidate = current.length - 1;
      candidate >= 0;
      candidate -= 1
    ) {
      if (
        current[candidate].tools?.some(
          (tool) =>
            (tool.status === "running" || tool.status === "preparing") &&
            tool.name === finished.name,
        )
      ) {
        ownerIndex = candidate;
        break;
      }
    }
  }

  if (ownerIndex >= 0) {
    current[ownerIndex] = {
      ...current[ownerIndex],
      tools: finishTool(current[ownerIndex].tools, finished),
    };
    return current;
  }

  return updateAssistantIteration(current, iteration, "tool", (item) => ({
    ...item,
    tools: finishTool(item.tools, finished),
  }));
}

export function completeIterationTools(
  iterations: AssistantIteration[] | undefined,
  status: ToolActivity["status"],
  errorMessage?: string,
): AssistantIteration[] {
  return (iterations ?? []).map((iteration) => ({
    ...iteration,
    tools: iteration.tools?.map((tool) =>
      tool.status === "running" || tool.status === "preparing"
        ? { ...tool, status, errorMessage }
        : tool,
    ),
  }));
}

export function streamedDelta(frame: AgentEventFrame): string | null {
  if (!STREAM_TEXT_EVENT_KINDS.has(frame.kind)) return null;
  const delta = frame.payload.delta;
  return typeof delta === "string" ? delta : null;
}

export function appendPendingAgentFrame(
  frames: AgentEventFrame[],
  frame: AgentEventFrame,
): void {
  const delta = streamedDelta(frame);
  const previous = frames.at(-1);
  const previousDelta = previous ? streamedDelta(previous) : null;
  if (
    delta !== null &&
    previous &&
    previousDelta !== null &&
    previous.kind === frame.kind &&
    previous.iteration === frame.iteration
  ) {
    frames[frames.length - 1] = {
      ...previous,
      payload: {
        ...previous.payload,
        delta: previousDelta + delta,
      },
      timestamp: frame.timestamp,
    };
    return;
  }
  frames.push(frame);
}

function takeCodePointPrefix(
  value: string,
  limit: number,
): { prefix: string; rest: string; count: number } {
  if (limit <= 0 || !value) {
    return { prefix: "", rest: value, count: 0 };
  }

  let end = 0;
  let count = 0;
  for (const character of value) {
    if (count >= limit) break;
    end += character.length;
    count += 1;
  }
  return {
    prefix: value.slice(0, end),
    rest: value.slice(end),
    count,
  };
}

export function takeAgentFramesForPaint(
  frames: AgentEventFrame[],
  textBudget: number,
): { painted: AgentEventFrame[]; textCount: number } {
  const painted: AgentEventFrame[] = [];
  let remainingBudget = textBudget;
  let textCount = 0;

  while (frames.length > 0) {
    const frame = frames[0];
    const delta = streamedDelta(frame);
    if (delta === null) {
      painted.push(frame);
      frames.shift();
      continue;
    }
    if (remainingBudget <= 0) break;

    const taken = takeCodePointPrefix(delta, remainingBudget);
    if (taken.count === 0) {
      frames.shift();
      continue;
    }
    painted.push({
      ...frame,
      payload: { ...frame.payload, delta: taken.prefix },
    });
    textCount += taken.count;
    remainingBudget -= taken.count;

    if (taken.rest) {
      frames[0] = {
        ...frame,
        payload: { ...frame.payload, delta: taken.rest },
      };
      break;
    }
    frames.shift();
  }

  return { painted, textCount };
}

export function applyAgentEventFrames(
  messages: UiMessage[],
  assistantId: string,
  frames: AgentEventFrame[],
): UiMessage[] {
  const assistantIndex = messages.findIndex(
    (message) => message.id === assistantId,
  );
  if (assistantIndex < 0) return messages;

  const original = messages[assistantIndex];
  let updated = original;

  for (const frame of frames) {
    if (
      frame.kind === "model.stream.content_delta" ||
      frame.kind === "model.stream.refusal_delta"
    ) {
      const delta = frame.payload.delta;
      if (typeof delta !== "string") continue;
      updated = {
        ...updated,
        iterations: updateAssistantIteration(
          updated.iterations,
          frame.iteration,
          "model",
          (modelIteration) => ({
            ...modelIteration,
            content: modelIteration.content + delta,
          }),
        ),
      };
      continue;
    }

    if (frame.kind === "model.stream.reasoning_delta") {
      const delta = frame.payload.delta;
      if (typeof delta !== "string") continue;
      updated = {
        ...updated,
        iterations: updateAssistantIteration(
          updated.iterations,
          frame.iteration,
          "model",
          (modelIteration) => ({
            ...modelIteration,
            reasoning: (modelIteration.reasoning ?? "") + delta,
          }),
        ),
      };
      continue;
    }

    if (frame.kind === "model.stream.tool_call_delta") {
      updated = {
        ...updated,
        iterations: updateAssistantIteration(
          updated.iterations,
          frame.iteration,
          "tool",
          (modelIteration) => ({
            ...modelIteration,
            tools: prepareTool(
              modelIteration.tools,
              frame.payload,
              frame.iteration,
            ),
          }),
        ),
      };
      continue;
    }

    if (frame.kind === "tool.call.started") {
      const tool = startedTool(frame.payload);
      if (!tool) continue;
      updated = {
        ...updated,
        iterations: updateAssistantIteration(
          updated.iterations,
          frame.iteration,
          "tool",
          (modelIteration) => ({
            ...modelIteration,
            tools: startTool(modelIteration.tools, tool),
          }),
        ),
      };
      continue;
    }

    if (frame.kind === "tool.call.finished") {
      const tool = finishedTool(frame.payload);
      if (!tool) continue;
      updated = {
        ...updated,
        iterations: finishIterationTool(
          updated.iterations,
          frame.iteration,
          tool,
        ),
      };
      continue;
    }

    if (frame.kind === "model.response.finished") {
      const response = asRecord(frame.payload.message);
      const reasoning = response?.reasoning_content;
      if (typeof reasoning !== "string" || !reasoning) continue;
      updated = {
        ...updated,
        iterations: updateAssistantIteration(
          updated.iterations,
          frame.iteration,
          "model",
          (modelIteration) =>
            modelIteration.reasoning
              ? modelIteration
              : { ...modelIteration, reasoning },
        ),
      };
    }
  }

  if (updated === original) return messages;
  const next = [...messages];
  next[assistantIndex] = updated;
  return next;
}
