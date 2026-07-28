import { useCallback, useEffect, useRef, useState } from "react";
import { ChatSocket } from "../api/chat-socket";
import {
  completeIterationTools,
  createMessageId,
  frameSessionId,
} from "../lib/chat-events";
import type { PendingSessionInfo } from "../lib/session-tree";
import type {
  ChatFrame,
  ToolActivity,
  UiMessage,
} from "../types/api";
import { useAgentFrameBuffer } from "./useAgentFrameBuffer";
import { useStableCallback } from "./useStableCallback";

interface StartRunOptions {
  sessionId: string;
  task: string;
  workspace: string | null;
  fallbackMessages: UiMessage[];
}

interface UseChatRuntimeOptions {
  onNotify: (message: string) => void;
  onSessionCreated: (
    sessionId: string,
    session: PendingSessionInfo,
  ) => void;
  onSessionSettled: () => void;
}

export function useChatRuntime({
  onNotify,
  onSessionCreated: handleSessionCreated,
  onSessionSettled: handleSessionSettled,
}: UseChatRuntimeOptions) {
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [runningSessionIds, setRunningSessionIds] = useState<ReadonlySet<string>>(
    () => new Set(),
  );
  const [stoppingSessionIds, setStoppingSessionIds] = useState<
    ReadonlySet<string>
  >(() => new Set());
  const [messages, setMessages] = useState<UiMessage[]>([]);
  const notify = useStableCallback(onNotify);
  const reportSessionCreated = useStableCallback(handleSessionCreated);
  const onSessionSettled = useStableCallback(handleSessionSettled);

  const socketsRef = useRef(new Map<string, ChatSocket>());
  const activeSessionIdRef = useRef<string | null>(null);
  const runningSessionIdsRef = useRef(new Set<string>());
  const messagesBySessionRef = useRef(new Map<string, UiMessage[]>());
  const assistantIdsRef = useRef(new Map<string, string>());
  const frameHandlerRef = useRef<
    (
      sessionId: string,
      sourceSessionId: string,
      frame: ChatFrame,
    ) => void
  >(() => undefined);

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

  const getAssistantId = useCallback(
    (sessionId: string) => assistantIdsRef.current.get(sessionId),
    [],
  );
  const {
    flush: flushPendingAgentFrames,
    forget: forgetPendingAgentFrames,
    queue: queueAgentFrame,
  } = useAgentFrameBuffer({
    getAssistantId,
    updateSessionMessages,
  });

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

  const failRun = useCallback(
    (sessionId: string, message: string) => {
      if (!runningSessionIdsRef.current.has(sessionId)) return;
      flushPendingAgentFrames(sessionId);
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
                  durationSeconds:
                    item.durationSeconds ??
                    (item.startedAt
                      ? Math.max(0, (Date.now() - item.startedAt) / 1000)
                      : undefined),
                  error: true,
                }
              : item,
          ),
        );
      }
      notify(message);
    },
    [
      flushPendingAgentFrames,
      notify,
      setSessionRunning,
      setSessionStopping,
      updateSessionMessages,
    ],
  );

  frameHandlerRef.current = (sessionId, sourceSessionId, frame) => {
    if (frame.type === "session_created") {
      if (runningSessionIdsRef.current.has(sessionId)) return;

      const assistantId = createMessageId();
      assistantIdsRef.current.set(sessionId, assistantId);
      messagesBySessionRef.current.set(sessionId, [
        {
          id: createMessageId(),
          role: "user",
          content: frame.content,
        },
        {
          id: assistantId,
          role: "assistant",
          content: "",
          iterations: [],
          startedAt: Date.now(),
        },
      ]);
      reportSessionCreated(sessionId, {
        workspace: frame.workspace,
        title: frame.title,
        parentSessionId:
          sourceSessionId === sessionId ? undefined : sourceSessionId,
      });
      setSessionRunning(sessionId, true);
      return;
    }

    if (frame.type === "event") {
      queueAgentFrame(sessionId, frame);
      return;
    }

    flushPendingAgentFrames(sessionId);

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
              durationSeconds:
                typeof frame.duration_s === "number"
                  ? frame.duration_s
                  : item.startedAt
                    ? Math.max(0, (Date.now() - item.startedAt) / 1000)
                    : undefined,
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
      onSessionSettled();
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
                  durationSeconds:
                    item.startedAt
                      ? Math.max(0, (Date.now() - item.startedAt) / 1000)
                      : item.durationSeconds,
                  stopped: true,
                }
              : item,
          ),
        );
      }
      setSessionRunning(sessionId, false);
      setSessionStopping(sessionId, false);
      onSessionSettled();
      return;
    }

    if (frame.type === "error") {
      failRun(sessionId, frame.message);
    }
  };

  const connectSocket = useCallback(
    async (sessionId: string): Promise<ChatSocket> => {
      const existing = socketsRef.current.get(sessionId);
      if (existing?.connected) return existing;
      existing?.close();

      const socket = new ChatSocket(sessionId, {
        onFrame: (frame) =>
          frameHandlerRef.current(
            frameSessionId(frame, sessionId),
            sessionId,
            frame,
          ),
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
    },
    [failRun],
  );

  const setCachedSessionMessages = useCallback(
    (sessionId: string, sessionMessages: UiMessage[]) => {
      messagesBySessionRef.current.set(sessionId, sessionMessages);
      if (activeSessionIdRef.current === sessionId) {
        setMessages(sessionMessages);
      }
    },
    [],
  );

  const getSessionMessages = useCallback(
    (sessionId: string) => messagesBySessionRef.current.get(sessionId),
    [],
  );

  const isSessionRunning = useCallback(
    (sessionId: string) => runningSessionIdsRef.current.has(sessionId),
    [],
  );

  const forgetSessions = useCallback(
    (sessionIds: Iterable<string>) => {
      const ids = [...sessionIds];
      for (const sessionId of ids) {
        socketsRef.current.get(sessionId)?.close();
        socketsRef.current.delete(sessionId);
        messagesBySessionRef.current.delete(sessionId);
        assistantIdsRef.current.delete(sessionId);
      }
      forgetPendingAgentFrames(ids);
    },
    [forgetPendingAgentFrames],
  );

  const startRun = useCallback(
    async ({
      sessionId,
      task,
      workspace,
      fallbackMessages,
    }: StartRunOptions) => {
      if (runningSessionIdsRef.current.has(sessionId)) return;
      const assistantId = createMessageId();
      const sessionMessages =
        messagesBySessionRef.current.get(sessionId) ?? fallbackMessages;
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
      if (activeSessionIdRef.current === sessionId) setMessages(runMessages);

      try {
        const socket = await connectSocket(sessionId);
        socket.send(task, workspace);
      } catch (error) {
        failRun(
          sessionId,
          error instanceof Error ? error.message : "消息发送失败",
        );
      }
    },
    [connectSocket, failRun, setSessionRunning, setSessionStopping],
  );

  const stopActiveRun = useCallback(() => {
    const sessionId = activeSessionIdRef.current;
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
  }, [notify, setSessionStopping, stoppingSessionIds]);

  useEffect(
    () => () => {
      socketsRef.current.forEach((socket) => socket.close());
      socketsRef.current.clear();
    },
    [],
  );

  return {
    activeSessionId,
    displaySession,
    forgetSessions,
    getSessionMessages,
    isSessionRunning,
    messages,
    runningSessionIds,
    setCachedSessionMessages,
    startRun,
    stopActiveRun,
    stoppingSessionIds,
  };
}
