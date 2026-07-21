import { useCallback, useEffect, useRef, useState } from "react";
import { ChatSocket } from "./api/chat-socket";
import {
  createSession,
  deleteSession,
  getHealth,
  getSession,
  getSessions,
  getSettings,
  updateSettings,
} from "./api/http";
import { ChatView } from "./components/ChatView";
import { Composer } from "./components/Composer";
import { HomeView } from "./components/HomeView";
import { SettingsView } from "./components/SettingsView";
import { Sidebar } from "./components/Sidebar";
import type {
  AssistantIteration,
  ChatFrame,
  SessionSummary,
  Settings,
  SettingsUpdate,
  StoredMessage,
  ToolActivity,
  UiMessage,
} from "./types/api";

type BootstrapStatus = "loading" | "ready" | "error";

const wait = (milliseconds: number) =>
  new Promise((resolve) => window.setTimeout(resolve, milliseconds));

function isProviderConfigured(settings: Settings): boolean {
  return (
    settings.provider.api_key_configured &&
    Boolean(settings.provider.model?.trim())
  );
}

function createMessageId(): string {
  return crypto.randomUUID();
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

function storedToolError(content: unknown): string | null {
  const parsed = parseArguments(content);
  const document = asRecord(parsed);
  const error = asRecord(document?.error);
  return typeof error?.message === "string" ? error.message : null;
}

function historyMessages(messages: StoredMessage[]): UiMessage[] {
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
      } else {
        result.push({
          id: `history-${index}`,
          role: "assistant",
          content: "",
          iterations: [modelIteration],
        });
      }
      return;
    }

    if (message.role === "tool") {
      const callId =
        typeof message.tool_call_id === "string" ? message.tool_call_id : "";
      const tool = callId ? toolsByCallId.get(callId) : undefined;
      if (tool) {
        const errorMessage = storedToolError(message.content);
        tool.status = errorMessage ? "error" : "completed";
        tool.errorMessage = errorMessage || undefined;
      }
    }
  });

  return result;
}

function workspaceLabel(path: string | null | undefined): string {
  if (!path) return "默认工作区";
  const parts = path.split(/[\\/]/).filter(Boolean);
  return parts.at(-1) || path;
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
  const index = current.findIndex(
    (tool) =>
      tool.id === finished.id ||
      ((tool.status === "running" || tool.status === "preparing") &&
        tool.name === finished.name),
  );
  if (index === -1) return [...current, finished];
  current[index] = { ...current[index], ...finished };
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
  const ownerIndex = current.findIndex((item) =>
    item.tools?.some(
      (tool) =>
        tool.id === finished.id ||
        ((tool.status === "running" || tool.status === "preparing") &&
          tool.name === finished.name),
    ),
  );

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

function completeIterationTools(
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

export default function App() {
  const [bootstrapStatus, setBootstrapStatus] =
    useState<BootstrapStatus>("loading");
  const [bootstrapAttempt, setBootstrapAttempt] = useState(0);
  const [settings, setSettings] = useState<Settings | null>(null);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [runningSessionIds, setRunningSessionIds] = useState<ReadonlySet<string>>(
    () => new Set(),
  );
  const [stoppingSessionIds, setStoppingSessionIds] = useState<
    ReadonlySet<string>
  >(() => new Set());
  const [pendingSessionIds, setPendingSessionIds] = useState<
    ReadonlySet<string>
  >(() => new Set());
  const [messages, setMessages] = useState<UiMessage[]>([]);
  const [input, setInput] = useState("");
  const [showSettings, setShowSettings] = useState(false);
  const [deleteSessionId, setDeleteSessionId] = useState<string | null>(null);
  const [toast, setToast] = useState("");

  const socketsRef = useRef(new Map<string, ChatSocket>());
  const activeSessionIdRef = useRef<string | null>(null);
  const runningSessionIdsRef = useRef(new Set<string>());
  const messagesBySessionRef = useRef(new Map<string, UiMessage[]>());
  const assistantIdsRef = useRef(new Map<string, string>());
  const sessionsLoadVersionRef = useRef(0);
  const sessionSelectionVersionRef = useRef(0);
  const frameHandlerRef = useRef<(sessionId: string, frame: ChatFrame) => void>(
    () => undefined,
  );
  const toastTimerRef = useRef<number | null>(null);

  const notify = useCallback((message: string) => {
    setToast(message);
    if (toastTimerRef.current !== null) {
      window.clearTimeout(toastTimerRef.current);
    }
    toastTimerRef.current = window.setTimeout(() => setToast(""), 2200);
  }, []);

  const displaySession = useCallback(
    (sessionId: string | null, sessionMessages: UiMessage[]) => {
      activeSessionIdRef.current = sessionId;
      if (sessionId) messagesBySessionRef.current.set(sessionId, sessionMessages);
      setActiveSessionId(sessionId);
      setMessages(sessionMessages);
    },
    [],
  );

  const updateSessionMessages = useCallback(
    (sessionId: string, update: (current: UiMessage[]) => UiMessage[]) => {
      const current = messagesBySessionRef.current.get(sessionId) ?? [];
      const next = update(current);
      messagesBySessionRef.current.set(sessionId, next);
      if (activeSessionIdRef.current === sessionId) {
        setMessages(next);
      }
    },
    [],
  );

  const setSessionRunning = useCallback(
    (sessionId: string, running: boolean) => {
      const next = new Set(runningSessionIdsRef.current);
      if (running) next.add(sessionId);
      else next.delete(sessionId);
      runningSessionIdsRef.current = next;
      setRunningSessionIds(next);
    },
    [],
  );

  const setSessionStopping = useCallback(
    (sessionId: string, stopping: boolean) => {
      setStoppingSessionIds((current) => {
        const next = new Set(current);
        if (stopping) next.add(sessionId);
        else next.delete(sessionId);
        return next;
      });
    },
    [],
  );

  const loadSessions = useCallback(async () => {
    const version = ++sessionsLoadVersionRef.current;
    const loaded = await getSessions();
    if (version !== sessionsLoadVersionRef.current) return;
    setSessions(loaded);
    const persistedIds = new Set(loaded.map((session) => session.session_id));
    setPendingSessionIds((pending) => {
      const next = new Set(pending);
      persistedIds.forEach((sessionId) => next.delete(sessionId));
      return next;
    });
  }, []);

  const failRun = useCallback(
    (sessionId: string, message: string) => {
      if (!runningSessionIdsRef.current.has(sessionId)) return;
      socketsRef.current.get(sessionId)?.close();
      socketsRef.current.delete(sessionId);
      setSessionRunning(sessionId, false);
      setSessionStopping(sessionId, false);
      const assistantId = assistantIdsRef.current.get(sessionId);
      assistantIdsRef.current.delete(sessionId);
      if (assistantId) {
        updateSessionMessages(sessionId, (current) =>
          current.map((item) =>
            item.id === assistantId
              ? {
                  ...item,
                  iterations: (() => {
                    const completed = completeIterationTools(
                      item.iterations,
                      "error",
                      message,
                    );
                    const last = completed.at(-1);
                    if (!last || last.tools?.length) {
                      return [
                        ...completed,
                        {
                          id: createMessageId(),
                          iteration: null,
                          content: `请求失败：${message}`,
                        },
                      ];
                    }
                    if (last.content) return completed;
                    completed[completed.length - 1] = {
                      ...last,
                      content: `请求失败：${message}`,
                    };
                    return completed;
                  })(),
                  error: true,
                }
              : item,
          ),
        );
      }
      notify(message);
    },
    [notify, setSessionRunning, setSessionStopping, updateSessionMessages],
  );

  frameHandlerRef.current = (sessionId, frame) => {
    if (frame.type === "event") {
      if (
        frame.kind === "model.stream.content_delta" ||
        frame.kind === "model.stream.refusal_delta"
      ) {
        const delta = frame.payload.delta;
        const assistantId = assistantIdsRef.current.get(sessionId);
        if (assistantId && typeof delta === "string") {
          updateSessionMessages(sessionId, (current) =>
            current.map((item) =>
              item.id === assistantId
                ? {
                    ...item,
                    iterations: updateAssistantIteration(
                      item.iterations,
                      frame.iteration,
                      "model",
                      (modelIteration) => ({
                        ...modelIteration,
                        content: modelIteration.content + delta,
                      }),
                    ),
                  }
                : item,
            ),
          );
        }
      } else if (frame.kind === "model.stream.reasoning_delta") {
        const delta = frame.payload.delta;
        const assistantId = assistantIdsRef.current.get(sessionId);
        if (assistantId && typeof delta === "string") {
          updateSessionMessages(sessionId, (current) =>
            current.map((item) =>
              item.id === assistantId
                ? {
                    ...item,
                    iterations: updateAssistantIteration(
                      item.iterations,
                      frame.iteration,
                      "model",
                      (modelIteration) => ({
                        ...modelIteration,
                        reasoning: (modelIteration.reasoning ?? "") + delta,
                      }),
                    ),
                  }
                : item,
            ),
          );
        }
      } else if (frame.kind === "model.stream.tool_call_delta") {
        const assistantId = assistantIdsRef.current.get(sessionId);
        if (assistantId) {
          updateSessionMessages(sessionId, (current) =>
            current.map((item) =>
              item.id === assistantId
                ? {
                    ...item,
                    iterations: updateAssistantIteration(
                      item.iterations,
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
                  }
                : item,
            ),
          );
        }
      } else if (frame.kind === "tool.call.started") {
        const tool = startedTool(frame.payload);
        const assistantId = assistantIdsRef.current.get(sessionId);
        if (tool && assistantId) {
          updateSessionMessages(sessionId, (current) =>
            current.map((item) =>
              item.id === assistantId
                ? {
                    ...item,
                    iterations: updateAssistantIteration(
                      item.iterations,
                      frame.iteration,
                      "tool",
                      (modelIteration) => ({
                        ...modelIteration,
                        tools: startTool(modelIteration.tools, tool),
                      }),
                    ),
                  }
                : item,
            ),
          );
        }
      } else if (frame.kind === "tool.call.finished") {
        const tool = finishedTool(frame.payload);
        const assistantId = assistantIdsRef.current.get(sessionId);
        if (tool && assistantId) {
          updateSessionMessages(sessionId, (current) =>
            current.map((item) =>
              item.id === assistantId
                ? {
                    ...item,
                    iterations: finishIterationTool(
                      item.iterations,
                      frame.iteration,
                      tool,
                    ),
                  }
                : item,
            ),
          );
        }
      } else if (frame.kind === "model.response.finished") {
        const response = asRecord(frame.payload.message);
        const reasoning = response?.reasoning_content;
        const assistantId = assistantIdsRef.current.get(sessionId);
        if (assistantId && typeof reasoning === "string" && reasoning) {
          updateSessionMessages(sessionId, (current) =>
            current.map((item) =>
              item.id !== assistantId
                ? item
                : {
                    ...item,
                    iterations: updateAssistantIteration(
                      item.iterations,
                      frame.iteration,
                      "model",
                      (modelIteration) =>
                        modelIteration.reasoning
                          ? modelIteration
                          : { ...modelIteration, reasoning },
                    ),
                  },
            ),
          );
        }
      }
      return;
    }

    if (frame.type === "result") {
      const assistantId = assistantIdsRef.current.get(sessionId);
      if (assistantId) {
        updateSessionMessages(sessionId, (current) =>
          current.map((item) => {
            if (item.id !== assistantId) return item;
            const status: ToolActivity["status"] = frame.error
              ? "error"
              : "completed";
            let iterations = completeIterationTools(
              item.iterations,
              status,
              frame.error?.message,
            );

            const finalContent =
              frame.final_content ?? frame.error?.message ?? "";
            if (finalContent) {
              const last = iterations.at(-1);
              if (!last) {
                iterations = [
                  {
                    id: createMessageId(),
                    iteration: null,
                    content: finalContent,
                  },
                ];
              } else if (!last.content) {
                if (last.tools?.length) {
                  iterations.push({
                    id: createMessageId(),
                    iteration: null,
                    content: finalContent,
                  });
                } else {
                  iterations[iterations.length - 1] = {
                    ...last,
                    content: finalContent,
                  };
                }
              } else if (
                last.tools?.length &&
                last.content.trim() !== finalContent.trim()
              ) {
                iterations.push({
                  id: createMessageId(),
                  iteration: null,
                  content: finalContent,
                });
              }
            }
            return {
              ...item,
              iterations:
                iterations.length > 0
                  ? iterations
                  : [
                      {
                        id: createMessageId(),
                        iteration: null,
                        content: "请求未返回内容",
                      },
                    ],
              error: Boolean(frame.error),
            };
          }),
        );
      }
      assistantIdsRef.current.delete(sessionId);
      socketsRef.current.get(sessionId)?.close();
      socketsRef.current.delete(sessionId);
      setSessionRunning(sessionId, false);
      setSessionStopping(sessionId, false);
      if (frame.error) notify(frame.error.message);
      void loadSessions().catch(() => notify("会话列表刷新失败"));
      return;
    }

    if (frame.type === "cancelled") {
      const assistantId = assistantIdsRef.current.get(sessionId);
      assistantIdsRef.current.delete(sessionId);
      socketsRef.current.get(sessionId)?.close();
      socketsRef.current.delete(sessionId);
      if (assistantId) {
        updateSessionMessages(sessionId, (current) =>
          current.map((item) =>
            item.id === assistantId
              ? {
                  ...item,
                  iterations: completeIterationTools(
                    item.iterations,
                    "cancelled",
                  ),
                  stopped: true,
                }
              : item,
          ),
        );
      }
      setSessionRunning(sessionId, false);
      setSessionStopping(sessionId, false);
      void loadSessions().catch(() => notify("会话列表刷新失败"));
      return;
    }

    if (frame.type === "error") {
      failRun(sessionId, frame.message);
    }
  };

  useEffect(() => {
    let cancelled = false;

    async function bootstrap() {
      setBootstrapStatus("loading");
      let connected = false;
      for (let attempt = 0; attempt < 12 && !cancelled; attempt += 1) {
        try {
          const health = await getHealth();
          if (health.status === "ok" && health.runtime === "ready") {
            connected = true;
            break;
          }
        } catch {
          // The Tauri sidecar may still be starting.
        }
        await wait(500);
      }

      if (!connected || cancelled) {
        if (!cancelled) setBootstrapStatus("error");
        return;
      }

      try {
        const [loadedSettings, loadedSessions] = await Promise.all([
          getSettings(),
          getSessions(),
        ]);
        if (cancelled) return;
        setSettings(loadedSettings);
        setSessions(loadedSessions);
        setShowSettings(!isProviderConfigured(loadedSettings));
        setBootstrapStatus("ready");
      } catch {
        if (!cancelled) setBootstrapStatus("error");
      }
    }

    void bootstrap();
    return () => {
      cancelled = true;
    };
  }, [bootstrapAttempt]);

  useEffect(
    () => () => {
      socketsRef.current.forEach((socket) => socket.close());
      socketsRef.current.clear();
      if (toastTimerRef.current !== null) {
        window.clearTimeout(toastTimerRef.current);
      }
    },
    [],
  );

  useEffect(() => {
    function handleShortcut(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "n") {
        event.preventDefault();
        document.getElementById("newChat")?.click();
      }
    }
    document.addEventListener("keydown", handleShortcut);
    return () => document.removeEventListener("keydown", handleShortcut);
  }, []);

  async function connectSocket(sessionId: string): Promise<ChatSocket> {
    const existing = socketsRef.current.get(sessionId);
    if (existing?.connected) return existing;
    existing?.close();

    const socket = new ChatSocket(sessionId, {
      onFrame: (frame) => frameHandlerRef.current(sessionId, frame),
      onDisconnect: () => {
        if (socketsRef.current.get(sessionId) === socket) {
          socketsRef.current.delete(sessionId);
        }
        failRun(sessionId, "聊天连接已中断");
      },
    });
    socketsRef.current.set(sessionId, socket);
    try {
      await socket.connect();
      return socket;
    } catch (error) {
      if (socketsRef.current.get(sessionId) === socket) {
        socketsRef.current.delete(sessionId);
      }
      socket.close();
      throw error;
    }
  }

  async function newChat() {
    if (!settings || !isProviderConfigured(settings)) {
      setShowSettings(true);
      notify("请先完成 API Key 和模型设置");
      return;
    }
    try {
      const selectionVersion = ++sessionSelectionVersionRef.current;
      const sessionId = await createSession();
      messagesBySessionRef.current.set(sessionId, []);
      setPendingSessionIds((current) => new Set(current).add(sessionId));
      if (selectionVersion !== sessionSelectionVersionRef.current) return;
      displaySession(sessionId, []);
      setInput("");
      setShowSettings(false);
    } catch (error) {
      notify(error instanceof Error ? error.message : "新建会话失败");
    }
  }

  async function selectSession(sessionId: string) {
    const selectionVersion = ++sessionSelectionVersionRef.current;
    if (sessionId === activeSessionId) {
      setShowSettings(false);
      return;
    }

    if (
      runningSessionIdsRef.current.has(sessionId) ||
      pendingSessionIds.has(sessionId)
    ) {
      displaySession(
        sessionId,
        messagesBySessionRef.current.get(sessionId) ?? [],
      );
      setShowSettings(false);
      return;
    }

    try {
      const detail = await getSession(sessionId);
      if (selectionVersion !== sessionSelectionVersionRef.current) return;
      displaySession(sessionId, historyMessages(detail.messages));
      setShowSettings(false);
    } catch (error) {
      notify(error instanceof Error ? error.message : "会话加载失败");
    }
  }

  function requestDeleteSession(sessionId: string) {
    if (runningSessionIdsRef.current.has(sessionId)) {
      notify("请先停止这个会话的任务");
      return;
    }
    setDeleteSessionId(sessionId);
  }

  async function confirmDeleteSession() {
    const sessionId = deleteSessionId;
    if (!sessionId) return;
    setDeleteSessionId(null);
    try {
      await deleteSession(sessionId);
      socketsRef.current.get(sessionId)?.close();
      socketsRef.current.delete(sessionId);
      messagesBySessionRef.current.delete(sessionId);
      assistantIdsRef.current.delete(sessionId);
      setSessions((current) =>
        current.filter((session) => session.session_id !== sessionId),
      );
      setPendingSessionIds((current) => {
        const next = new Set(current);
        next.delete(sessionId);
        return next;
      });
      if (sessionId === activeSessionId) {
        displaySession(null, []);
      }
    } catch (error) {
      notify(error instanceof Error ? error.message : "会话删除失败");
    }
  }

  async function sendMessage() {
    const task = input.trim();
    if (!task) return;
    if (!settings || !isProviderConfigured(settings)) {
      setShowSettings(true);
      notify("请先完成 API Key 和模型设置");
      return;
    }

    let sessionId = activeSessionId;
    if (sessionId && runningSessionIdsRef.current.has(sessionId)) return;
    try {
      if (!sessionId) {
        const createdSessionId = await createSession();
        sessionId = createdSessionId;
        displaySession(createdSessionId, []);
        setPendingSessionIds((current) =>
          new Set(current).add(createdSessionId),
        );
      }

      const assistantId = createMessageId();
      const sessionMessages =
        messagesBySessionRef.current.get(sessionId) ?? messages;
      const runMessages: UiMessage[] = [
        ...sessionMessages,
        { id: createMessageId(), role: "user", content: task },
        {
          id: assistantId,
          role: "assistant",
          content: "",
          iterations: [],
        },
      ];
      assistantIdsRef.current.set(sessionId, assistantId);
      messagesBySessionRef.current.set(sessionId, runMessages);
      setSessionRunning(sessionId, true);
      setSessionStopping(sessionId, false);
      setInput("");
      setMessages(runMessages);

      const socket = await connectSocket(sessionId);
      socket.send(task);
    } catch (error) {
      if (sessionId) {
        failRun(
          sessionId,
          error instanceof Error ? error.message : "消息发送失败",
        );
      }
    }
  }

  function stopRun() {
    const sessionId = activeSessionId;
    if (
      !sessionId ||
      !runningSessionIdsRef.current.has(sessionId) ||
      stoppingSessionIds.has(sessionId)
    ) {
      return;
    }
    setSessionStopping(sessionId, true);
    try {
      const socket = socketsRef.current.get(sessionId);
      if (!socket?.connected) throw new Error("聊天连接不可用");
      socket.cancel();
    } catch (error) {
      setSessionStopping(sessionId, false);
      notify(error instanceof Error ? error.message : "停止运行失败");
    }
  }

  async function saveSettings(update: SettingsUpdate) {
    const saved = await updateSettings(update);
    setSettings(saved);
    setShowSettings(false);
    notify("设置已保存");
  }

  const isViewingRunningSession = Boolean(
    activeSessionId && runningSessionIds.has(activeSessionId),
  );
  const isViewingStoppingSession = Boolean(
    activeSessionId && stoppingSessionIds.has(activeSessionId),
  );
  const hasRunningSessions = runningSessionIds.size > 0;
  const deleteSessionTitle = deleteSessionId
    ? sessions.find((session) => session.session_id === deleteSessionId)?.title
    : null;
  const pendingSessions = [...pendingSessionIds].map((sessionId) => {
    const firstUserMessage = messagesBySessionRef.current
      .get(sessionId)
      ?.find((message) => message.role === "user");
    const title =
      typeof firstUserMessage?.content === "string"
        ? firstUserMessage.content.trim()
        : "";
    return { sessionId, title: title || "新对话" };
  });

  return (
    <main className="app-shell" aria-label="BumbleHive 对话工作台">
      <Sidebar
        sessions={sessions}
        activeSessionId={activeSessionId}
        pendingSessions={pendingSessions}
        runningSessionIds={runningSessionIds}
        disabled={bootstrapStatus !== "ready"}
        settingsDisabled={bootstrapStatus !== "ready" || hasRunningSessions}
        sessionSelectionDisabled={bootstrapStatus !== "ready"}
        onNewChat={() => void newChat()}
        onSelectSession={(sessionId) => void selectSession(sessionId)}
        onDeleteSession={requestDeleteSession}
        onOpenSettings={() => {
          if (hasRunningSessions) {
            notify("请等待所有会话任务完成");
          } else {
            setShowSettings(true);
          }
        }}
      />

      <section
        className={`main-panel${messages.length ? " chat-active" : ""}`}
      >
        {bootstrapStatus === "loading" ? (
          <div className="connection-state">
            <span className="connection-spinner" aria-hidden="true" />
            <h1>正在连接 BumbleHive</h1>
            <p>桌面服务启动后会自动进入工作台</p>
          </div>
        ) : null}

        {bootstrapStatus === "error" ? (
          <div className="connection-state">
            <h1>无法连接桌面服务</h1>
            <p>请确认 BumbleHive Server 已经启动</p>
            <button
              className="primary-button"
              type="button"
              onClick={() => setBootstrapAttempt((attempt) => attempt + 1)}
            >
              重新连接
            </button>
          </div>
        ) : null}

        {bootstrapStatus === "ready" && settings ? (
          showSettings ? (
            <SettingsView
              settings={settings}
              canCancel={isProviderConfigured(settings)}
              onCancel={() => setShowSettings(false)}
              onSave={saveSettings}
            />
          ) : (
            <>
              {messages.length ? (
                <ChatView
                  key={activeSessionId ?? "active-chat"}
                  messages={messages}
                  isStreaming={isViewingRunningSession}
                />
              ) : (
                <HomeView onSelectPrompt={setInput} />
              )}
              <Composer
                value={input}
                model={settings.provider.model ?? ""}
                workspace={workspaceLabel(settings.runtime?.workspace)}
                disabled={bootstrapStatus !== "ready"}
                isStreaming={isViewingRunningSession}
                isStopping={isViewingStoppingSession}
                onChange={setInput}
                onSubmit={() => void sendMessage()}
                onStop={stopRun}
                onOpenSettings={() => setShowSettings(true)}
              />
            </>
          )
        ) : null}

        {deleteSessionId ? (
          <div className="confirm-backdrop" role="presentation">
            <section
              className="confirm-dialog"
              role="dialog"
              aria-modal="true"
              aria-labelledby="deleteSessionTitle"
            >
              <h2 id="deleteSessionTitle">删除会话？</h2>
              <p>
                {deleteSessionTitle
                  ? `“${deleteSessionTitle}”将被永久删除。`
                  : "该会话将被永久删除。"}
              </p>
              <div className="confirm-actions">
                <button
                  className="secondary-button"
                  type="button"
                  onClick={() => setDeleteSessionId(null)}
                >
                  取消
                </button>
                <button
                  className="danger-button"
                  type="button"
                  onClick={() => void confirmDeleteSession()}
                >
                  删除
                </button>
              </div>
            </section>
          </div>
        ) : null}

        <div
          className={`toast${toast ? " show" : ""}`}
          role="status"
          aria-live="polite"
        >
          {toast}
        </div>
      </section>
    </main>
  );
}
