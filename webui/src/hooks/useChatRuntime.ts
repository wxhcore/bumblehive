import { useCallback, useEffect, useRef, useState } from "react";
import { getSession } from "../api/http";
import { ChatSocket } from "../api/chat-socket";
import { applyQuestionFrame } from "../lib/questions";
import {
  applyApprovalFrame,
  applyPendingMessageStatus,
  completeIterationTools,
  createMessageId,
  frameSessionId,
  historyMessages,
  restoreRunningMessages,
} from "../lib/chat-events";
import type { PendingSessionInfo } from "../lib/session-tree";
import type {
  ApprovalMode,
  ChatFrame,
  PendingApproval,
  PendingChatMessage,
  ToolActivity,
  UiMessage,
  UserQuestion,
} from "../types/api";
import { useAgentFrameBuffer } from "./useAgentFrameBuffer";
import { useStableCallback } from "./useStableCallback";

interface StartRunOptions {
  sessionId: string;
  task: string;
  approvalMode: ApprovalMode;
  workspace: string | null;
  fallbackMessages: UiMessage[];
}

interface UseChatRuntimeOptions {
  getParentSessionId: (sessionId: string) => string | undefined;
  onNotify: (message: string) => void;
  onSessionCreated: (
    sessionId: string,
    session: PendingSessionInfo,
  ) => void;
  onSessionSettled: () => void;
}

export function useChatRuntime({
  getParentSessionId,
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
  const [approvals, setApprovals] = useState<PendingApproval[]>([]);
  const [questions, setQuestions] = useState<UserQuestion[]>([]);
  const [pendingBySession, setPendingBySession] = useState(new Map<string, PendingChatMessage[]>());
  const [disconnectedSessions, setDisconnectedSessions] = useState(new Set<string>());
  const pendingRef = useRef(new Map<string, PendingChatMessage[]>());
  const [messages, setMessages] = useState<UiMessage[]>([]);
  const notify = useStableCallback(onNotify);
  const reportSessionCreated = useStableCallback(handleSessionCreated);
  const onSessionSettled = useStableCallback(handleSessionSettled);
  const parentSessionIdFor = useStableCallback(getParentSessionId);

  const socketsRef = useRef(new Map<string, ChatSocket>());
  const activeSessionIdRef = useRef<string | null>(null);
  const runningSessionIdsRef = useRef(new Set<string>());
  const messagesBySessionRef = useRef(new Map<string, UiMessage[]>());
  const activeMessageIdsRef = useRef(new Map<string, string>());
  const backgroundParentsRef = useRef(new Map<string, string>());
  const assistantIdsRef = useRef(new Map<string, string>());
  const frameHandlerRef = useRef<
    (
      sessionId: string,
      sourceSessionId: string,
      frame: ChatFrame,
    ) => void | Promise<void>
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
      else {
        next.delete(sessionId);
        setApprovals((current) =>
          current.filter((item) => item.session_id !== sessionId),
        );
      }
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
      setSessionRunning(sessionId, false);
      setSessionStopping(sessionId, false);
      const assistantId = assistantIdsRef.current.get(sessionId);
      assistantIdsRef.current.delete(sessionId);
      activeMessageIdsRef.current.delete(sessionId);
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

  const updatePending = useCallback((sessionId: string, items: PendingChatMessage[]) => {
    pendingRef.current.set(sessionId, items);
    setPendingBySession(new Map(pendingRef.current));
  }, []);

  const restoreHistory = useCallback(async (sessionId: string) => {
    try {
      const detail = await getSession(sessionId);
      updateSessionMessages(sessionId, () => historyMessages(detail.messages));
    } catch {
      // Existing live messages remain usable if a history refresh fails.
    }
  }, [updateSessionMessages]);

  frameHandlerRef.current = async (sessionId, sourceSessionId, frame) => {
    if (frame.type === "ready" || frame.type === "question_request" ||
      frame.type === "question_closed" ||
      (frame.type === "error" && frame.scope === "input" && frame.question_id)) {
      setQuestions((current) => applyQuestionFrame(current, sessionId, frame));
    }
    if (frame.type === "question_request" || frame.type === "question_closed" ||
      (frame.type === "error" && frame.scope === "input" && frame.question_id)) return;
    if (frame.type === "ready") {
      flushPendingAgentFrames(sessionId);
      await restoreHistory(sessionId);
      updatePending(sessionId, frame.pending ?? []);
      setDisconnectedSessions((current) => {
        const next = new Set(current); next.delete(sessionId); return next;
      });
      setSessionRunning(sessionId, Boolean(frame.running));
      setSessionStopping(sessionId, false);
      assistantIdsRef.current.delete(sessionId);
      activeMessageIdsRef.current.delete(sessionId);
      if (frame.active_message_id) activeMessageIdsRef.current.set(sessionId, frame.active_message_id);
      if (frame.running) {
        updateSessionMessages(sessionId, (current) => {
          const next = restoreRunningMessages(current, frame);
          assistantIdsRef.current.set(sessionId, next.at(-1)!.id);
          return next;
        });
      }
      setApprovals((current) => [
        ...current.filter((item) => item.sourceSessionId !== sourceSessionId),
        ...(frame.approvals ?? []).map((item) => ({ ...item, sourceSessionId, submitting: false })),
      ]);
      const children = frame.running_subagents ?? [];
      const running = new Set(children.map((child) => child.session_id));
      for (const [childId, parentId] of backgroundParentsRef.current) {
        if (parentId === sessionId && !running.has(childId)) {
          backgroundParentsRef.current.delete(childId);
          flushPendingAgentFrames(childId);
          setSessionRunning(childId, false);
          assistantIdsRef.current.delete(childId);
          await restoreHistory(childId);
        }
      }
      for (const child of children) {
        backgroundParentsRef.current.set(child.session_id, sessionId);
        reportSessionCreated(child.session_id, {
          workspace: child.workspace, title: child.title, parentSessionId: sessionId,
        });
        flushPendingAgentFrames(child.session_id);
        await restoreHistory(child.session_id);
        updateSessionMessages(child.session_id, (current) => {
          const restored = restoreRunningMessages(current, {
            type: "ready", session_id: child.session_id, running: true,
            started_at: child.started_at,
            active_message: { message_id: child.session_id, content: child.content },
          });
          assistantIdsRef.current.set(child.session_id, restored.at(-1)!.id);
          return restored;
        });
        setSessionRunning(child.session_id, true);
      }
      return;
    }

    if (frame.type === "message_status") {
      flushPendingAgentFrames(sessionId);
      const items = pendingRef.current.get(sessionId) ?? [];
      updatePending(sessionId, applyPendingMessageStatus(items, frame));
      if (frame.status === "started") {
        if (activeMessageIdsRef.current.get(sessionId) === frame.message_id) return;
        activeMessageIdsRef.current.set(sessionId, frame.message_id);
        const assistantId = createMessageId();
        assistantIdsRef.current.set(sessionId, assistantId);
        updateSessionMessages(sessionId, (current) => [...current,
          { id: frame.message_id, role: "user", content: frame.content },
          { id: assistantId, role: "assistant", content: "", iterations: [], startedAt: Date.now() },
        ]);
        setSessionRunning(sessionId, true);
        setSessionStopping(sessionId, false);
      } else if (frame.status === "steered") {
        // Keep the current run/assistant; the completed history restores exact message order.
        notify("引导已发送");
      }
      return;
    }

    if (frame.type === "session_created") {
      if (frame.background) backgroundParentsRef.current.set(sessionId, sourceSessionId);
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

    if (frame.type === "approval_request" || frame.type === "approval_resolved") {
      const assistantId = assistantIdsRef.current.get(sessionId);
      if (!assistantId || !runningSessionIdsRef.current.has(sessionId)) return;
      updateSessionMessages(sessionId, (current) =>
        applyApprovalFrame(current, assistantId, frame),
      );
      if (frame.type === "approval_request") {
        setApprovals((current) =>
          current.some((item) => item.approval_id === frame.approval_id)
            ? current
            : [...current, { ...frame, sourceSessionId, submitting: false }],
        );
      } else {
        setApprovals((current) =>
          current.filter((item) => item.approval_id !== frame.approval_id),
        );
      }
      return;
    }

    if (frame.type === "result") {
      backgroundParentsRef.current.delete(sessionId);
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
      activeMessageIdsRef.current.delete(sessionId);
      setSessionRunning(sessionId, false);
      setSessionStopping(sessionId, false);
      if (frame.error) notify(frame.error.message);
      if (!(pendingRef.current.get(sessionId)?.length)) await restoreHistory(sessionId);
      onSessionSettled();
      return;
    }

    if (frame.type === "cancelled") {
      backgroundParentsRef.current.delete(sessionId);
      updatePending(sessionId, (pendingRef.current.get(sessionId) ?? []).map((item) => ({
        ...item, submitting: false,
      })));
      const assistantId = assistantIdsRef.current.get(sessionId);
      assistantIdsRef.current.delete(sessionId);
      activeMessageIdsRef.current.delete(sessionId);
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
      if (frame.scope === "input") {
        updatePending(sessionId, (pendingRef.current.get(sessionId) ?? []).map((item) =>
          item.message_id === frame.message_id ? { ...item, submitting: false } : item));
        notify(frame.message);
      } else {
        backgroundParentsRef.current.delete(sessionId);
        updatePending(sessionId, (pendingRef.current.get(sessionId) ?? []).map((item) => ({
          ...item, submitting: false,
        })));
        failRun(sessionId, frame.message);
      }
    }
  };

  const connectSocket = useCallback(
    async (sessionId: string): Promise<ChatSocket> => {
      const existing = socketsRef.current.get(sessionId);
      if (existing) {
        await existing.connect();
        return existing;
      }

      const socket = new ChatSocket(sessionId, {
        onFrame: (frame) =>
          frameHandlerRef.current(
            frameSessionId(frame, sessionId),
            sessionId,
            frame,
          ),
        onDisconnect: () => {
          setDisconnectedSessions((current) => new Set(current).add(sessionId));
          setQuestions((current) => current.map((item) =>
            item.session_id === sessionId ? { ...item, submitting: false } : item));
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
    [],
  );

  useEffect(() => {
    // Running subagents receive their events through the parent's connection.
    if (!activeSessionId) return;
    const connect = async () => {
      const parentId = parentSessionIdFor(activeSessionId);
      if (parentId) await connectSocket(parentId);
      if (!runningSessionIdsRef.current.has(activeSessionId) || socketsRef.current.has(activeSessionId)) {
        await connectSocket(activeSessionId);
      }
    };
    void connect().catch(() => undefined);
  }, [activeSessionId, connectSocket, parentSessionIdFor, runningSessionIds]);

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
        activeMessageIdsRef.current.delete(sessionId);
        backgroundParentsRef.current.delete(sessionId);
        setSessionRunning(sessionId, false);
        pendingRef.current.delete(sessionId);
      }
      setPendingBySession(new Map(pendingRef.current));
      setApprovals((current) =>
        current.filter((item) => !ids.includes(item.session_id)),
      );
      setQuestions((current) => current.filter((item) => !ids.includes(item.session_id)));
      forgetPendingAgentFrames(ids);
    },
    [forgetPendingAgentFrames, setSessionRunning],
  );

  const startRun = useCallback(
    async ({
      sessionId,
      task,
      approvalMode,
      workspace,
      fallbackMessages,
    }: StartRunOptions) => {
      if (!messagesBySessionRef.current.has(sessionId)) {
        messagesBySessionRef.current.set(sessionId, fallbackMessages);
      }
      const messageId = createMessageId();
      try {
        const parentId = parentSessionIdFor(sessionId);
        if (parentId) await connectSocket(parentId);
        if (runningSessionIdsRef.current.has(sessionId) && (
          backgroundParentsRef.current.has(sessionId) || !socketsRef.current.has(sessionId)
        )) {
          notify("子任务仍在运行，请等待完成后再发送消息");
          return;
        }
        const socket = await connectSocket(sessionId);
        await socket.whenSynced();
        updatePending(sessionId, [...(pendingRef.current.get(sessionId) ?? []),
          { message_id: messageId, content: task, submitting: true }]);
        socket.send(task, workspace, approvalMode, messageId);
      } catch (error) {
        updatePending(sessionId, (pendingRef.current.get(sessionId) ?? []).filter((item) => item.message_id !== messageId));
        notify(error instanceof Error ? error.message : "消息发送失败");
      }
    },
    [connectSocket, notify, parentSessionIdFor, updatePending],
  );

  const actOnPending = useCallback((messageId: string, type: "steer" | "remove_pending") => {
    const sessionId = activeSessionIdRef.current;
    if (!sessionId) return;
    const items = pendingRef.current.get(sessionId) ?? [];
    if (items.find((item) => item.message_id === messageId)?.submitting) return;
    try {
      const socket = socketsRef.current.get(sessionId);
      if (!socket?.connected) throw new Error("聊天连接不可用");
      socket.updatePending(type, messageId);
      updatePending(sessionId, items.map((item) => item.message_id === messageId ? { ...item, submitting: true } : item));
    } catch (error) {
      notify(error instanceof Error ? error.message : "操作失败");
    }
  }, [notify, updatePending]);

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

  const decideApproval = useCallback(
    (approval: PendingApproval, approved: boolean) => {
      if (approval.submitting) return;
      try {
        const socket = socketsRef.current.get(approval.sourceSessionId);
        if (!socket?.connected) throw new Error("聊天连接不可用");
        socket.decideApproval(approval.approval_id, approved);
        setApprovals((current) =>
          current.map((item) =>
            item.approval_id === approval.approval_id
              ? { ...item, submitting: true }
              : item,
          ),
        );
      } catch (error) {
        notify(error instanceof Error ? error.message : "提交审批失败");
      }
    },
    [notify],
  );

  const answerQuestion = useCallback((question: UserQuestion, answer?: string) => {
    if (question.submitting ||
      (answer !== undefined && !answer.trim())) return;
    let errorMessage: string | undefined;
    try {
      const socket = socketsRef.current.get(question.session_id);
      if (!socket?.connected) throw new Error("聊天连接不可用，请重连后提交");
      socket.answerQuestion(question.question_id, answer);
    } catch (error) {
      errorMessage = error instanceof Error ? error.message : "回答提交失败";
    }
    setQuestions((current) => current.map((item) =>
      item.session_id === question.session_id && item.question_id === question.question_id
        ? { ...item, submitting: !errorMessage, error: errorMessage }
        : item));
  }, []);

  useEffect(
    () => () => {
      socketsRef.current.forEach((socket) => socket.close());
      socketsRef.current.clear();
    },
    [],
  );

  return {
    backgroundSessionIds: new Set([...runningSessionIds].filter((id) => backgroundParentsRef.current.has(id))),
    activeSessionId,
    pendingMessages: activeSessionId ? pendingBySession.get(activeSessionId) ?? [] : [],
    isDisconnected: activeSessionId ? disconnectedSessions.has(
      runningSessionIds.has(activeSessionId)
        ? backgroundParentsRef.current.get(activeSessionId) ?? activeSessionId : activeSessionId,
    ) : false,
    actOnPending,
    pendingApprovals: approvals.filter((item) => item.session_id === activeSessionId),
    questions: questions.filter((item) => item.session_id === activeSessionId),
    answerQuestion,
    decideApproval,
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
