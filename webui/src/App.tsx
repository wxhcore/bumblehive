import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { ChatSocket } from "./api/chat-socket";
import {
  createSession,
  deleteSession,
  getHealth,
  getModels,
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
import {
  MAX_SIDEBAR_WIDTH,
  MIN_SIDEBAR_WIDTH,
  useSidebarWidth,
} from "./hooks/useSidebarWidth";
import {
  isMacDesktop,
  pickWorkspaceDirectory,
  startWindowDrag,
} from "./lib/platform";
import {
  mergeDiscoveredWorkspaces,
  readSelectedWorkspace,
  readWorkspaceRegistry,
  removeKnownWorkspace,
  workspaceKey,
  workspaceLabel,
  writeSelectedWorkspace,
  writeWorkspaceRegistry,
} from "./lib/workspaces";
import type {
  AssistantIteration,
  ChatFrame,
  CreatedSession,
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

function useStableCallback<Args extends unknown[], Result>(
  callback: (...args: Args) => Result,
): (...args: Args) => Result {
  const callbackRef = useRef(callback);
  callbackRef.current = callback;
  return useCallback((...args: Args) => callbackRef.current(...args), []);
}

export default function App() {
  const [bootstrapStatus, setBootstrapStatus] =
    useState<BootstrapStatus>("loading");
  const [bootstrapAttempt, setBootstrapAttempt] = useState(0);
  const [settings, setSettings] = useState<Settings | null>(null);
  const [workspaceRegistry, setWorkspaceRegistry] = useState(
    readWorkspaceRegistry,
  );
  const [selectedWorkspace, setSelectedWorkspace] = useState<string | null>(
    readSelectedWorkspace,
  );
  const [availableModels, setAvailableModels] = useState<string[]>([]);
  const [modelSwitching, setModelSwitching] = useState(false);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [runningSessionIds, setRunningSessionIds] = useState<ReadonlySet<string>>(
    () => new Set(),
  );
  const [stoppingSessionIds, setStoppingSessionIds] = useState<
    ReadonlySet<string>
  >(() => new Set());
  const [pendingSessionWorkspaces, setPendingSessionWorkspaces] = useState<
    ReadonlyMap<string, string>
  >(() => new Map());
  const [messages, setMessages] = useState<UiMessage[]>([]);
  const [input, setInput] = useState("");
  const [showSettings, setShowSettings] = useState(false);
  const [focusSettingsWorkspace, setFocusSettingsWorkspace] =
    useState(false);
  const [deleteSessionId, setDeleteSessionId] = useState<string | null>(null);
  const [removeWorkspacePath, setRemoveWorkspacePath] = useState<string | null>(
    null,
  );
  const [toast, setToast] = useState("");
  const sidebar = useSidebarWidth();

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
  const modelListRequestIdRef = useRef(0);
  const blankSessionIdsRef = useRef(new Map<string, string>());
  const blankSessionRequestsRef = useRef(
    new Map<string, Promise<CreatedSession>>(),
  );
  const notify = useCallback((message: string) => {
    setToast(message);
    if (toastTimerRef.current !== null) {
      window.clearTimeout(toastTimerRef.current);
    }
    toastTimerRef.current = window.setTimeout(() => setToast(""), 2200);
  }, []);

  const loadAvailableModels = useCallback(async (currentSettings: Settings) => {
    const requestId = ++modelListRequestIdRef.current;
    const baseUrl = currentSettings.provider.base_url?.trim();
    setAvailableModels([]);
    if (!baseUrl) return;
    try {
      const response = await getModels({ base_url: baseUrl });
      if (requestId !== modelListRequestIdRef.current) return;
      setAvailableModels(
        Array.from(
          new Set(
            response.models
              .map((model) => model.trim())
              .filter((model) => Boolean(model)),
          ),
        ),
      );
    } catch {
      if (requestId === modelListRequestIdRef.current) {
        setAvailableModels([]);
      }
    }
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
    setWorkspaceRegistry((current) =>
      mergeDiscoveredWorkspaces(
        current,
        loaded.map((session) => ({
          path: session.workspace,
          createdAt: session.created_at,
        })),
      ),
    );
    const persistedIds = new Set(loaded.map((session) => session.session_id));
    setPendingSessionWorkspaces((pending) => {
      const next = new Map(pending);
      persistedIds.forEach((sessionId) => next.delete(sessionId));
      return next;
    });
  }, []);

  useEffect(() => {
    writeWorkspaceRegistry(workspaceRegistry);
  }, [workspaceRegistry]);

  useEffect(() => {
    writeSelectedWorkspace(selectedWorkspace);
  }, [selectedWorkspace]);

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
        const currentWorkspace = loadedSettings.runtime?.workspace?.trim();
        const discoveredRegistry = mergeDiscoveredWorkspaces(
          readWorkspaceRegistry(),
          [
            ...loadedSessions.map((session) => ({
              path: session.workspace,
              createdAt: session.created_at,
            })),
            ...(currentWorkspace
              ? [
                  {
                    path: currentWorkspace,
                    createdAt: Date.now() / 1000,
                  },
                ]
              : []),
          ],
        );
        const storedSelection = readSelectedWorkspace();
        const nextSelection =
          discoveredRegistry.items.find(
            (workspace) =>
              workspaceKey(workspace.path) === workspaceKey(storedSelection),
          )?.path ??
          discoveredRegistry.items.find(
            (workspace) =>
              workspaceKey(workspace.path) === workspaceKey(currentWorkspace),
          )?.path ??
          discoveredRegistry.items[0]?.path ??
          null;
        setSettings(loadedSettings);
        setWorkspaceRegistry(discoveredRegistry);
        setSelectedWorkspace(nextSelection);
        void loadAvailableModels(loadedSettings);
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
  }, [bootstrapAttempt, loadAvailableModels]);

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

  function workspaceForSession(sessionId: string | null): string | null {
    if (!sessionId) return null;
    return (
      pendingSessionWorkspaces.get(sessionId) ??
      sessions.find((session) => session.session_id === sessionId)
        ?.workspace ??
      null
    );
  }

  function rememberWorkspace(
    workspace: string | null | undefined,
    createdAt = Date.now() / 1000,
    restore = true,
  ) {
    const path = workspace?.trim();
    if (!path) return;
    setWorkspaceRegistry((current) =>
      mergeDiscoveredWorkspaces(
        current,
        [{ path, createdAt }],
        restore,
      ),
    );
  }

  function newChatWorkspace(): string | null {
    return (
      workspaceForSession(activeSessionIdRef.current) ??
      selectedWorkspace?.trim() ??
      null
    );
  }

  function reusableBlankSession(workspace: string | null): string | null {
    const targetKey = workspaceKey(workspace);
    const rememberedId = blankSessionIdsRef.current.get(targetKey);
    const rememberedWorkspace = rememberedId
      ? workspaceForSession(rememberedId)
      : null;
    if (
      rememberedId &&
      rememberedWorkspace &&
      workspaceKey(rememberedWorkspace) === targetKey &&
      !runningSessionIdsRef.current.has(rememberedId) &&
      (messagesBySessionRef.current.get(rememberedId)?.length ?? 0) === 0
    ) {
      return rememberedId;
    }
    if (rememberedId) {
      blankSessionIdsRef.current.delete(targetKey);
      blankSessionRequestsRef.current.delete(targetKey);
    }

    for (const [sessionId, pendingWorkspace] of pendingSessionWorkspaces) {
      if (
        workspaceKey(pendingWorkspace) === targetKey &&
        !runningSessionIdsRef.current.has(sessionId) &&
        (messagesBySessionRef.current.get(sessionId)?.length ?? 0) === 0
      ) {
        blankSessionIdsRef.current.set(targetKey, sessionId);
        return sessionId;
      }
    }

    const persisted = sessions.find(
      (session) =>
        workspaceKey(session.workspace) === targetKey &&
        session.message_count === 0 &&
        !runningSessionIdsRef.current.has(session.session_id) &&
        (messagesBySessionRef.current.get(session.session_id)?.length ?? 0) ===
          0,
    );
    if (!persisted) return null;
    blankSessionIdsRef.current.set(targetKey, persisted.session_id);
    return persisted.session_id;
  }

  function createBlankSession(
    workspace: string | null,
  ): Promise<CreatedSession> {
    const targetKey = workspaceKey(workspace);
    const existingRequest = blankSessionRequestsRef.current.get(targetKey);
    if (existingRequest) return existingRequest;

    const request = createSession(workspace)
      .then(async (created) => {
        blankSessionRequestsRef.current.delete(targetKey);
        if (workspaceKey(created.workspace) !== targetKey) {
          await deleteSession(created.session_id).catch(() => false);
          throw new Error(
            "服务端工作空间状态未更新，请重启 BumbleHive 后重试",
          );
        }
        blankSessionIdsRef.current.set(targetKey, created.session_id);
        return created;
      })
      .catch((error: unknown) => {
        blankSessionRequestsRef.current.delete(targetKey);
        throw error;
      });
    blankSessionRequestsRef.current.set(targetKey, request);
    return request;
  }

  function releaseBlankSession(sessionId: string) {
    for (const [workspace, rememberedId] of blankSessionIdsRef.current) {
      if (rememberedId !== sessionId) continue;
      blankSessionIdsRef.current.delete(workspace);
      blankSessionRequestsRef.current.delete(workspace);
      return;
    }
  }

  async function newChat(requestedWorkspace?: string | null) {
    if (!settings || !isProviderConfigured(settings)) {
      setShowSettings(true);
      notify("请先完成 API Key 和模型设置");
      return;
    }
    const workspace = requestedWorkspace?.trim() || newChatWorkspace();
    if (!workspace) {
      setShowSettings(true);
      notify("请先在设置中添加工作空间");
      return;
    }
    rememberWorkspace(workspace);
    setSelectedWorkspace(workspace);
    try {
      const selectionVersion = ++sessionSelectionVersionRef.current;
      const reusableSessionId = reusableBlankSession(workspace);
      if (reusableSessionId) {
        if (reusableSessionId !== activeSessionId) {
          displaySession(reusableSessionId, []);
          setInput("");
        }
        setShowSettings(false);
        return;
      }

      const created = await createBlankSession(workspace);
      messagesBySessionRef.current.set(created.session_id, []);
      setPendingSessionWorkspaces((current) =>
        new Map(current).set(created.session_id, created.workspace),
      );
      rememberWorkspace(created.workspace, Date.now() / 1000);
      if (selectionVersion !== sessionSelectionVersionRef.current) return;
      displaySession(created.session_id, []);
      setInput("");
      setShowSettings(false);
    } catch (error) {
      notify(error instanceof Error ? error.message : "新建会话失败");
    }
  }

  async function selectSession(sessionId: string) {
    const selectionVersion = ++sessionSelectionVersionRef.current;
    const sessionWorkspace = workspaceForSession(sessionId);
    if (sessionWorkspace) {
      rememberWorkspace(sessionWorkspace);
      setSelectedWorkspace(sessionWorkspace);
    }
    if (sessionId === activeSessionId) {
      setShowSettings(false);
      return;
    }

    if (
      runningSessionIdsRef.current.has(sessionId) ||
      pendingSessionWorkspaces.has(sessionId)
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
      rememberWorkspace(detail.workspace, detail.created_at);
      setSelectedWorkspace(detail.workspace);
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
      releaseBlankSession(sessionId);
      socketsRef.current.get(sessionId)?.close();
      socketsRef.current.delete(sessionId);
      messagesBySessionRef.current.delete(sessionId);
      assistantIdsRef.current.delete(sessionId);
      setSessions((current) =>
        current.filter((session) => session.session_id !== sessionId),
      );
      setPendingSessionWorkspaces((current) => {
        const next = new Map(current);
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

  function requestRemoveWorkspace(workspace: string) {
    const key = workspaceKey(workspace);
    const sessionIds = [
      ...sessions
        .filter((session) => workspaceKey(session.workspace) === key)
        .map((session) => session.session_id),
      ...[...pendingSessionWorkspaces]
        .filter(([, pendingWorkspace]) => workspaceKey(pendingWorkspace) === key)
        .map(([sessionId]) => sessionId),
    ];
    if (
      sessionIds.some((sessionId) =>
        runningSessionIdsRef.current.has(sessionId),
      )
    ) {
      notify("请先停止这个工作空间中正在运行的任务");
      return;
    }
    setRemoveWorkspacePath(workspace);
  }

  async function addWorkspace() {
    try {
      const workspace = await pickWorkspaceDirectory();
      if (workspace === undefined) {
        setFocusSettingsWorkspace(true);
        setShowSettings(true);
        notify("请在设置中填写工作区路径");
        return;
      }
      if (!workspace) return;

      rememberWorkspace(workspace, Date.now() / 1000, true);
      setSelectedWorkspace(workspace);
      displaySession(null, []);
      setInput("");
      setShowSettings(false);
    } catch (error) {
      notify(
        error instanceof Error ? error.message : "工作空间目录选择失败",
      );
    }
  }

  function confirmRemoveWorkspace() {
    const workspace = removeWorkspacePath;
    if (!workspace) return;
    setRemoveWorkspacePath(null);
    const key = workspaceKey(workspace);
    const remaining = workspaceRegistry.items.filter(
      (candidate) => workspaceKey(candidate.path) !== key,
    );
    setWorkspaceRegistry((current) =>
      removeKnownWorkspace(current, workspace),
    );
    if (workspaceKey(workspaceForSession(activeSessionId)) === key) {
      displaySession(null, []);
      setInput("");
    }
    if (workspaceKey(selectedWorkspace) === key) {
      setSelectedWorkspace(remaining[0]?.path ?? null);
    }
    if (remaining.length === 0) setShowSettings(true);
    notify(`${workspaceLabel(workspace)} 已从侧栏移除`);
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
    let taskWorkspace =
      workspaceForSession(sessionId) ??
      selectedWorkspace ??
      settings.runtime?.workspace ??
      null;
    if (sessionId && runningSessionIdsRef.current.has(sessionId)) return;
    try {
      if (!sessionId) {
        const workspace = newChatWorkspace();
        if (!workspace) {
          setShowSettings(true);
          notify("请先在设置中添加工作空间");
          return;
        }
        const created = await createBlankSession(
          workspace,
        );
        sessionId = created.session_id;
        taskWorkspace = created.workspace;
        rememberWorkspace(created.workspace, Date.now() / 1000);
        setSelectedWorkspace(created.workspace);
        displaySession(created.session_id, []);
        setPendingSessionWorkspaces((current) =>
          new Map(current).set(created.session_id, created.workspace),
        );
      }

      const assistantId = createMessageId();
      releaseBlankSession(sessionId);
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
          startedAt: Date.now(),
        },
      ];
      assistantIdsRef.current.set(sessionId, assistantId);
      messagesBySessionRef.current.set(sessionId, runMessages);
      setSessionRunning(sessionId, true);
      setSessionStopping(sessionId, false);
      setInput("");
      setMessages(runMessages);

      const socket = await connectSocket(sessionId);
      socket.send(task, taskWorkspace);
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
    const savedWorkspace = saved.runtime?.workspace?.trim() ?? null;
    const workspaceChanged =
      workspaceKey(savedWorkspace) !== workspaceKey(selectedWorkspace);
    setSettings(saved);
    if (savedWorkspace) {
      rememberWorkspace(savedWorkspace, Date.now() / 1000, true);
      setSelectedWorkspace(savedWorkspace);
    }
    if (workspaceChanged) {
      displaySession(null, []);
      setInput("");
    }
    void loadAvailableModels(saved);
    setFocusSettingsWorkspace(false);
    setShowSettings(false);
    notify("设置已保存");
  }

  async function selectModel(selectedModel: string) {
    if (
      !settings ||
      selectedModel === settings.provider.model ||
      runningSessionIdsRef.current.size > 0 ||
      modelSwitching
    ) {
      return;
    }
    setModelSwitching(true);
    try {
      const saved = await updateSettings({
        provider: {
          model: selectedModel,
        },
      });
      setSettings(saved);
      notify(`已切换到 ${selectedModel}`);
    } catch (error) {
      notify(error instanceof Error ? error.message : "模型切换失败");
    } finally {
      setModelSwitching(false);
    }
  }

  const isViewingRunningSession = Boolean(
    activeSessionId && runningSessionIds.has(activeSessionId),
  );
  const isViewingStoppingSession = Boolean(
    activeSessionId && stoppingSessionIds.has(activeSessionId),
  );
  const hasRunningSessions = runningSessionIds.size > 0;
  const selectableModels = useMemo(
    () =>
      settings
        ? Array.from(
            new Set(
              [settings.provider.model, ...availableModels].filter(
                (model): model is string => Boolean(model),
              ),
            ),
          )
        : [],
    [availableModels, settings],
  );
  const deleteSessionTitle = deleteSessionId
    ? sessions.find((session) => session.session_id === deleteSessionId)?.title
    : null;
  const activeFirstUserTitle =
    messages.find((message) => message.role === "user")?.content.trim() ?? "";
  const pendingSessions = useMemo(
    () =>
      [...pendingSessionWorkspaces].map(([sessionId, workspace]) => {
        const firstUserMessage = messagesBySessionRef.current
          .get(sessionId)
          ?.find((message) => message.role === "user");
        const title =
          typeof firstUserMessage?.content === "string"
            ? firstUserMessage.content.trim()
            : "";
        return { sessionId, workspace, title: title || "新对话" };
      }),
    [activeFirstUserTitle, activeSessionId, pendingSessionWorkspaces],
  );
  const activeSessionTitle = activeSessionId
    ? sessions.find((session) => session.session_id === activeSessionId)
        ?.title ??
      pendingSessions.find((session) => session.sessionId === activeSessionId)
        ?.title ??
      "新对话"
    : "新对话";
  const activeWorkspace =
    selectedWorkspace?.trim() ??
    workspaceForSession(activeSessionId) ??
    null;
  const isBlankChat =
    isMacDesktop &&
    bootstrapStatus === "ready" &&
    !showSettings &&
    messages.length === 0;
  const handleSidebarNewChat = useStableCallback(() => void newChat());
  const handleSidebarAddWorkspace = useStableCallback(
    () => void addWorkspace(),
  );
  const handleSidebarNewChatInWorkspace = useStableCallback(
    (workspace: string) => void newChat(workspace),
  );
  const handleSidebarRemoveWorkspace = useStableCallback(
    requestRemoveWorkspace,
  );
  const handleSidebarSelectSession = useStableCallback(
    (sessionId: string) => void selectSession(sessionId),
  );
  const handleSidebarDeleteSession = useStableCallback(requestDeleteSession);
  const handleSidebarOpenSettings = useStableCallback(() => {
    if (hasRunningSessions) {
      notify("请等待所有会话任务完成");
    } else {
      setFocusSettingsWorkspace(false);
      setShowSettings(true);
    }
  });
  const handleComposerSubmit = useStableCallback(() => void sendMessage());
  const handleComposerStop = useStableCallback(stopRun);
  const handleComposerSelectModel = useStableCallback(selectModel);
  const handleComposerOpenSettings = useStableCallback(() => {
    setFocusSettingsWorkspace(false);
    setShowSettings(true);
  });

  return (
    <main
      className={`app-shell${isMacDesktop ? " platform-macos" : ""}${
        isBlankChat ? " blank-chat" : ""
      }`}
      aria-label="BumbleHive 对话工作台"
      style={sidebar.style}
    >
      {isMacDesktop ? (
        <div
          className="desktop-titlebar"
          data-tauri-drag-region
          aria-hidden="true"
          onPointerDown={(event) => {
            if (event.button === 0) startWindowDrag();
          }}
        >
          <div className="desktop-titlebar-sidebar" />
          <div className="desktop-titlebar-divider" />
          <div className="desktop-titlebar-main">
            <span className="titlebar-folder-icon" />
            <span className="desktop-titlebar-title">
              {activeSessionTitle}
            </span>
          </div>
        </div>
      ) : null}

      <Sidebar
        workspaces={workspaceRegistry.items}
        sessions={sessions}
        activeSessionId={activeSessionId}
        currentWorkspace={activeWorkspace}
        pendingSessions={pendingSessions}
        runningSessionIds={runningSessionIds}
        disabled={bootstrapStatus !== "ready"}
        settingsDisabled={bootstrapStatus !== "ready" || hasRunningSessions}
        sessionSelectionDisabled={bootstrapStatus !== "ready"}
        onNewChat={handleSidebarNewChat}
        onAddWorkspace={handleSidebarAddWorkspace}
        onNewChatInWorkspace={handleSidebarNewChatInWorkspace}
        onRemoveWorkspace={handleSidebarRemoveWorkspace}
        onSelectSession={handleSidebarSelectSession}
        onDeleteSession={handleSidebarDeleteSession}
        onOpenSettings={handleSidebarOpenSettings}
      />

      <div
        className="sidebar-resizer"
        role="separator"
        aria-label="调整侧栏宽度"
        aria-orientation="vertical"
        aria-valuemin={MIN_SIDEBAR_WIDTH}
        aria-valuemax={MAX_SIDEBAR_WIDTH}
        aria-valuenow={Math.round(sidebar.width)}
        tabIndex={0}
        onDoubleClick={sidebar.reset}
        {...sidebar.resizerProps}
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
              currentWorkspace={activeWorkspace}
              canCancel={isProviderConfigured(settings)}
              focusWorkspace={focusSettingsWorkspace}
              onCancel={() => {
                setFocusSettingsWorkspace(false);
                setShowSettings(false);
              }}
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
                models={selectableModels}
                workspace={workspaceLabel(activeWorkspace)}
                disabled={bootstrapStatus !== "ready"}
                isStreaming={isViewingRunningSession}
                isStopping={isViewingStoppingSession}
                modelSwitchDisabled={hasRunningSessions || modelSwitching}
                onChange={setInput}
                onSubmit={handleComposerSubmit}
                onStop={handleComposerStop}
                onSelectModel={handleComposerSelectModel}
                onOpenSettings={handleComposerOpenSettings}
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

        {removeWorkspacePath ? (
          <div className="confirm-backdrop" role="presentation">
            <section
              className="confirm-dialog"
              role="dialog"
              aria-modal="true"
              aria-labelledby="removeWorkspaceTitle"
            >
              <h2 id="removeWorkspaceTitle">移除工作空间？</h2>
              <p>
                “{workspaceLabel(removeWorkspacePath)}”将从侧栏移除。本地文件夹和
                历史会话不会被删除；重新选择同一文件夹即可恢复。
              </p>
              <div className="confirm-actions">
                <button
                  className="secondary-button"
                  type="button"
                  onClick={() => setRemoveWorkspacePath(null)}
                >
                  取消
                </button>
                <button
                  className="danger-button"
                  type="button"
                  onClick={confirmRemoveWorkspace}
                >
                  移除
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
