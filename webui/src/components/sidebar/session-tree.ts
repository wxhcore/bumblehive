import {
  workspaceKey,
  workspaceLabel,
  type KnownWorkspace,
} from "../../lib/workspaces";
import type { SessionSummary } from "../../types/api";
import type {
  PendingSession,
  SidebarSession,
  WorkspaceGroup,
} from "./types";

function includesQuery(value: string, query: string): boolean {
  return value.toLocaleLowerCase().includes(query);
}

function compareCreatedAt(left: number, right: number): number {
  if (left === right) return 0;
  if (!Number.isFinite(left)) return 1;
  if (!Number.isFinite(right)) return -1;
  return left - right;
}

function sessionParent(
  session: SidebarSession,
  sessionsById: ReadonlyMap<string, SidebarSession>,
): SidebarSession | null {
  if (!session.parentId) return null;
  const parent = sessionsById.get(session.parentId);
  if (!parent) return null;

  const visited = new Set([session.id]);
  let current: SidebarSession | undefined = parent;
  while (current) {
    if (visited.has(current.id)) return null;
    visited.add(current.id);
    current = current.parentId
      ? sessionsById.get(current.parentId)
      : undefined;
  }
  return parent;
}

function sortSessionTree(sessions: SidebarSession[]): void {
  sessions.sort(
    (left, right) =>
      compareCreatedAt(right.createdAt, left.createdAt) ||
      left.id.localeCompare(right.id),
  );
  sessions.forEach((session) => sortSessionTree(session.children));
}

function filterSessionTree(
  session: SidebarSession,
  query: string,
): SidebarSession | null {
  if (includesQuery(session.searchableText, query)) return session;
  const children = session.children.flatMap((child) => {
    const match = filterSessionTree(child, query);
    return match ? [match] : [];
  });
  return children.length ? { ...session, children } : null;
}

export function branchIsRunning(
  session: SidebarSession,
  runningSessionIds: ReadonlySet<string>,
): boolean {
  return (
    runningSessionIds.has(session.id) ||
    session.children.some((child) =>
      branchIsRunning(child, runningSessionIds),
    )
  );
}

export function buildWorkspaceGroups(
  workspaces: KnownWorkspace[],
  sessions: SessionSummary[],
  pendingSessions: PendingSession[],
  query: string,
): WorkspaceGroup[] {
  const persistedIds = new Set(
    sessions.map((session) => session.session_id),
  );
  const byWorkspace = new Map<string, WorkspaceGroup>();

  function groupFor(
    path: string | null | undefined,
    createdAt = Number.POSITIVE_INFINITY,
  ): WorkspaceGroup {
    const key = workspaceKey(path);
    const existing = byWorkspace.get(key);
    if (existing) {
      existing.createdAt = Math.min(existing.createdAt, createdAt);
      return existing;
    }
    const group = {
      key,
      path: path?.trim() || "",
      label: workspaceLabel(path),
      createdAt,
      sessions: [],
    };
    byWorkspace.set(key, group);
    return group;
  }

  for (const workspace of workspaces) {
    groupFor(workspace.path, workspace.createdAt);
  }
  const visibleWorkspaceKeys = new Set(
    workspaces.map((workspace) => workspaceKey(workspace.path)),
  );
  for (const session of sessions) {
    if (!visibleWorkspaceKeys.has(workspaceKey(session.workspace))) continue;
    const createdAt = Number.isFinite(session.created_at)
      ? session.created_at
      : session.updated_at;
    const title = session.title || session.last_message || "未命名会话";
    groupFor(session.workspace, createdAt).sessions.push({
      id: session.session_id,
      parentId: session.parent_session_id?.trim() || null,
      title,
      searchableText: `${title} ${session.last_message}`,
      createdAt,
      children: [],
    });
  }
  for (const pending of pendingSessions) {
    if (persistedIds.has(pending.sessionId)) continue;
    if (!visibleWorkspaceKeys.has(workspaceKey(pending.workspace))) continue;
    groupFor(pending.workspace).sessions.push({
      id: pending.sessionId,
      parentId: pending.parentSessionId?.trim() || null,
      title: pending.title,
      searchableText: pending.title,
      createdAt: Number.POSITIVE_INFINITY,
      children: [],
    });
  }

  const normalizedQuery = query.trim().toLocaleLowerCase();
  const result = [...byWorkspace.values()]
    .sort(
      (left, right) =>
        compareCreatedAt(left.createdAt, right.createdAt) ||
        left.label.localeCompare(right.label),
    )
    .map((group) => {
      const sessionsById = new Map(
        group.sessions.map((session) => [session.id, session]),
      );
      const roots: SidebarSession[] = [];
      for (const session of group.sessions) {
        const parent = sessionParent(session, sessionsById);
        if (parent) parent.children.push(session);
        else roots.push(session);
      }
      sortSessionTree(roots);
      return { ...group, sessions: roots };
    });
  if (!normalizedQuery) return result;

  return result.flatMap((group) => {
    const workspaceMatches =
      includesQuery(group.label, normalizedQuery) ||
      includesQuery(group.path, normalizedQuery);
    const matchingSessions = workspaceMatches
      ? group.sessions
      : group.sessions.flatMap((session) => {
          const match = filterSessionTree(session, normalizedQuery);
          return match ? [match] : [];
        });
    return matchingSessions.length
      ? [{ ...group, sessions: matchingSessions }]
      : [];
  });
}
