import type { SessionSummary } from "../types/api";

export interface PendingSessionInfo {
  workspace: string;
  title?: string;
  parentSessionId?: string;
}

export function sessionBranchIds(
  rootSessionId: string,
  sessions: readonly SessionSummary[],
  pendingSessions: ReadonlyMap<string, PendingSessionInfo>,
): Set<string> {
  const childrenByParent = new Map<string, string[]>();
  const addChild = (sessionId: string, parentSessionId?: string | null) => {
    const parentId = parentSessionId?.trim();
    if (!parentId) return;
    const children = childrenByParent.get(parentId);
    if (children) children.push(sessionId);
    else childrenByParent.set(parentId, [sessionId]);
  };
  sessions.forEach((session) =>
    addChild(session.session_id, session.parent_session_id),
  );
  pendingSessions.forEach((pending, sessionId) =>
    addChild(sessionId, pending.parentSessionId),
  );

  const branchIds = new Set([rootSessionId]);
  const pendingIds = [rootSessionId];
  for (let index = 0; index < pendingIds.length; index += 1) {
    for (const childId of childrenByParent.get(pendingIds[index]) ?? []) {
      if (branchIds.has(childId)) continue;
      branchIds.add(childId);
      pendingIds.push(childId);
    }
  }
  return branchIds;
}
