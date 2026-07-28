import { useRef } from "react";
import { createSession, deleteSession } from "../api/http";
import { workspaceKey } from "../lib/workspaces";
import type { PendingSessionInfo } from "../lib/session-tree";
import type {
  CreatedSession,
  SessionSummary,
  UiMessage,
} from "../types/api";

interface UseBlankSessionsOptions {
  sessions: SessionSummary[];
  pendingSessions: ReadonlyMap<string, PendingSessionInfo>;
  workspaceForSession: (sessionId: string) => string | null;
  getSessionMessages: (sessionId: string) => UiMessage[] | undefined;
  isSessionRunning: (sessionId: string) => boolean;
}

export function useBlankSessions({
  sessions,
  pendingSessions,
  workspaceForSession,
  getSessionMessages,
  isSessionRunning,
}: UseBlankSessionsOptions) {
  const sessionIdsRef = useRef(new Map<string, string>());
  const requestsRef = useRef(
    new Map<string, Promise<CreatedSession>>(),
  );

  function reusableSession(workspace: string | null): string | null {
    const targetKey = workspaceKey(workspace);
    const rememberedId = sessionIdsRef.current.get(targetKey);
    const rememberedWorkspace = rememberedId
      ? workspaceForSession(rememberedId)
      : null;
    if (
      rememberedId &&
      rememberedWorkspace &&
      workspaceKey(rememberedWorkspace) === targetKey &&
      !isSessionRunning(rememberedId) &&
      (getSessionMessages(rememberedId)?.length ?? 0) === 0
    ) {
      return rememberedId;
    }
    if (rememberedId) {
      sessionIdsRef.current.delete(targetKey);
      requestsRef.current.delete(targetKey);
    }

    for (const [sessionId, pending] of pendingSessions) {
      if (
        workspaceKey(pending.workspace) === targetKey &&
        !isSessionRunning(sessionId) &&
        (getSessionMessages(sessionId)?.length ?? 0) === 0
      ) {
        sessionIdsRef.current.set(targetKey, sessionId);
        return sessionId;
      }
    }

    const persisted = sessions.find(
      (session) =>
        workspaceKey(session.workspace) === targetKey &&
        session.message_count === 0 &&
        !isSessionRunning(session.session_id) &&
        (getSessionMessages(session.session_id)?.length ?? 0) === 0,
    );
    if (!persisted) return null;
    sessionIdsRef.current.set(targetKey, persisted.session_id);
    return persisted.session_id;
  }

  function create(workspace: string | null): Promise<CreatedSession> {
    const targetKey = workspaceKey(workspace);
    const existingRequest = requestsRef.current.get(targetKey);
    if (existingRequest) return existingRequest;

    const request = createSession(workspace)
      .then(async (created) => {
        requestsRef.current.delete(targetKey);
        if (workspaceKey(created.workspace) !== targetKey) {
          await deleteSession(created.session_id).catch(() => false);
          throw new Error(
            "服务端工作空间状态未更新，请重启 BumbleHive 后重试",
          );
        }
        sessionIdsRef.current.set(targetKey, created.session_id);
        return created;
      })
      .catch((error: unknown) => {
        requestsRef.current.delete(targetKey);
        throw error;
      });
    requestsRef.current.set(targetKey, request);
    return request;
  }

  function release(sessionId: string) {
    for (const [workspace, rememberedId] of sessionIdsRef.current) {
      if (rememberedId !== sessionId) continue;
      sessionIdsRef.current.delete(workspace);
      requestsRef.current.delete(workspace);
      return;
    }
  }

  return {
    create,
    release,
    reusableSession,
  };
}
