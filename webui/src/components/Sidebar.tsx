import {
  memo,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  workspaceKey,
  workspaceLabel,
  type KnownWorkspace,
} from "../lib/workspaces";
import type { SessionSummary } from "../types/api";

export interface PendingSession {
  sessionId: string;
  workspace: string;
  title: string;
  parentSessionId?: string;
}

interface SidebarProps {
  workspaces: KnownWorkspace[];
  sessions: SessionSummary[];
  activeSessionId: string | null;
  currentWorkspace: string | null;
  pendingSessions: PendingSession[];
  runningSessionIds: ReadonlySet<string>;
  disabled: boolean;
  settingsDisabled: boolean;
  sessionSelectionDisabled: boolean;
  onNewChat: () => void;
  onAddWorkspace: () => void;
  onNewChatInWorkspace: (workspace: string) => void;
  onRemoveWorkspace: (workspace: string) => void;
  onSelectSession: (sessionId: string) => void;
  onDeleteSession: (sessionId: string) => void;
  onOpenSettings: () => void;
}

interface SidebarSession {
  id: string;
  parentId: string | null;
  title: string;
  searchableText: string;
  createdAt: number;
  children: SidebarSession[];
}

interface WorkspaceGroup {
  key: string;
  path: string;
  label: string;
  createdAt: number;
  sessions: SidebarSession[];
}

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

function branchIsRunning(
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

function SidebarChevron({ expanded }: { expanded: boolean }) {
  return (
    <svg
      className={`sidebar-chevron${expanded ? " expanded" : ""}`}
      viewBox="0 0 12 12"
      aria-hidden="true"
      focusable="false"
    >
      <path d="M4.125 2.25 7.875 6 4.125 9.75" />
    </svg>
  );
}

interface SessionBranchProps {
  session: SidebarSession;
  depth: number;
  activeSessionId: string | null;
  expandedSessionIds: ReadonlySet<string>;
  runningSessionIds: ReadonlySet<string>;
  searching: boolean;
  sessionSelectionDisabled: boolean;
  onToggle: (sessionId: string) => void;
  onSelect: (sessionId: string) => void;
  onDelete: (sessionId: string) => void;
}

function SessionBranch({
  session,
  depth,
  activeSessionId,
  expandedSessionIds,
  runningSessionIds,
  searching,
  sessionSelectionDisabled,
  onToggle,
  onSelect,
  onDelete,
}: SessionBranchProps) {
  const hasChildren = session.children.length > 0;
  const expanded =
    hasChildren &&
    (searching || expandedSessionIds.has(session.id));
  const running = runningSessionIds.has(session.id);
  const branchRunning = branchIsRunning(session, runningSessionIds);

  return (
    <div className="session-branch">
      <div
        className={`conversation-row${depth ? " child-session" : ""}${
          hasChildren ? " has-children" : ""
        }`}
      >
        {depth ? (
          <span
            className={`session-bee-mark${running ? " running" : ""}`}
            aria-hidden="true"
          >
            <img alt="" src="/brand/bumblehive-bee.png" />
          </span>
        ) : null}
        <button
          className={`conversation${
            session.id === activeSessionId ? " active" : ""
          }${running ? " running" : ""}`}
          type="button"
          disabled={sessionSelectionDisabled}
          onClick={() => onSelect(session.id)}
          title={session.title}
        >
          {session.title}
        </button>
        {hasChildren ? (
          <button
            className="session-toggle"
            type="button"
            aria-label={`${expanded ? "折叠" : "展开"}${session.title}的 ${
              session.children.length
            } 个 Bee 会话`}
            aria-expanded={expanded}
            onClick={() => onToggle(session.id)}
          >
            <img alt="" src="/brand/bumblehive-bee.png" />
            <span>{session.children.length}</span>
            <SidebarChevron expanded={expanded} />
          </button>
        ) : null}
        <button
          className="session-delete"
          type="button"
          disabled={sessionSelectionDisabled || branchRunning}
          aria-label={`删除${session.title}`}
          onClick={() => onDelete(session.id)}
        >
          ×
        </button>
      </div>
      {expanded ? (
        <div className="session-children">
          {session.children.map((child) => (
            <SessionBranch
              key={child.id}
              session={child}
              depth={depth + 1}
              activeSessionId={activeSessionId}
              expandedSessionIds={expandedSessionIds}
              runningSessionIds={runningSessionIds}
              searching={searching}
              sessionSelectionDisabled={sessionSelectionDisabled}
              onToggle={onToggle}
              onSelect={onSelect}
              onDelete={onDelete}
            />
          ))}
        </div>
      ) : null}
    </div>
  );
}

export const Sidebar = memo(function Sidebar({
  workspaces,
  sessions,
  activeSessionId,
  currentWorkspace,
  pendingSessions,
  runningSessionIds,
  disabled,
  settingsDisabled,
  sessionSelectionDisabled,
  onNewChat,
  onAddWorkspace,
  onNewChatInWorkspace,
  onRemoveWorkspace,
  onSelectSession,
  onDeleteSession,
  onOpenSettings,
}: SidebarProps) {
  const [searchOpen, setSearchOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [collapsedWorkspaces, setCollapsedWorkspaces] = useState<
    ReadonlySet<string>
  >(() => new Set());
  const [expandedSessionIds, setExpandedSessionIds] = useState<
    ReadonlySet<string>
  >(() => new Set());
  const seenPendingSessionIdsRef = useRef(new Set<string>());

  useEffect(() => {
    const parentsToExpand: string[] = [];
    for (const session of pendingSessions) {
      if (seenPendingSessionIdsRef.current.has(session.sessionId)) continue;
      seenPendingSessionIdsRef.current.add(session.sessionId);
      if (session.parentSessionId) {
        parentsToExpand.push(session.parentSessionId);
      }
    }
    if (!parentsToExpand.length) return;
    setExpandedSessionIds((current) => {
      const next = new Set(current);
      parentsToExpand.forEach((sessionId) => next.add(sessionId));
      return next;
    });
  }, [pendingSessions]);

  const groups = useMemo(() => {
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
      const title =
        session.title || session.last_message || "未命名会话";
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
  }, [pendingSessions, query, sessions, workspaces]);

  function toggleWorkspace(key: string) {
    setCollapsedWorkspaces((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  function toggleSession(sessionId: string) {
    setExpandedSessionIds((current) => {
      const next = new Set(current);
      if (next.has(sessionId)) next.delete(sessionId);
      else next.add(sessionId);
      return next;
    });
  }

  const searching = Boolean(query.trim());

  return (
    <aside className="sidebar">
      <div className="brand" aria-label="BumbleHive">
        <img
          className="brand-lockup"
          src="/brand/bumblehive-sidebar.png"
          alt=""
          aria-hidden="true"
        />
      </div>

      <nav className="nav" aria-label="主导航">
        <button
          id="newChat"
          className="nav-button"
          type="button"
          disabled={disabled}
          onClick={onNewChat}
        >
          <span className="nav-icon plus-icon" aria-hidden="true" />
          <span>新建对话</span>
        </button>
        <button
          className="nav-button"
          type="button"
          aria-expanded={searchOpen}
          onClick={() => setSearchOpen((open) => !open)}
        >
          <span className="nav-icon search-icon" aria-hidden="true" />
          <span>搜索</span>
        </button>
      </nav>

      {searchOpen ? (
        <input
          className="session-search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="搜索项目或会话"
          aria-label="搜索项目或会话"
          autoFocus
        />
      ) : null}

      <section className="recent" aria-labelledby="projectTitle">
        <div className="project-heading-row">
          <span className="project-heading-label" id="projectTitle">
            项目
          </span>
          <button
            className="workspace-action project-add-workspace"
            type="button"
            disabled={disabled}
            aria-label="添加工作空间"
            title="添加工作空间"
            onClick={onAddWorkspace}
          >
            +
          </button>
        </div>
        <div className="conversations">
          {groups.map((group) => {
            const selected =
              workspaceKey(currentWorkspace) === group.key;
            const expanded =
              searching || !collapsedWorkspaces.has(group.key);
            const workspaceRunning = group.sessions.some((session) =>
              branchIsRunning(session, runningSessionIds),
            );
            return (
              <section
                className="workspace-group"
                key={group.key}
                aria-label={group.label}
              >
                <div className="workspace-heading-row">
                  <button
                    className="workspace-heading"
                    type="button"
                    title={group.path || group.label}
                    aria-expanded={expanded}
                    aria-current={selected ? "true" : undefined}
                    onClick={() => toggleWorkspace(group.key)}
                  >
                    <span className="sidebar-folder-icon" aria-hidden="true" />
                    <span className="workspace-heading-label">
                      {group.label}
                    </span>
                  </button>
                  <div className="workspace-actions">
                    <button
                      className="workspace-action workspace-remove"
                      type="button"
                      disabled={disabled || workspaceRunning}
                      aria-label={`移除工作空间 ${group.label}`}
                      title={
                        workspaceRunning
                          ? "工作空间中有任务正在运行"
                          : "从侧栏移除"
                      }
                      onClick={() => onRemoveWorkspace(group.path)}
                    >
                      ×
                    </button>
                    <button
                      className="workspace-action workspace-add-session"
                      type="button"
                      disabled={disabled}
                      aria-label={`在 ${group.label} 中新建会话`}
                      title="新建会话"
                      onClick={() => onNewChatInWorkspace(group.path)}
                    >
                      +
                    </button>
                  </div>
                </div>

                {expanded ? (
                  <div className="workspace-sessions">
                    {group.sessions.map((session) => (
                      <SessionBranch
                        key={session.id}
                        session={session}
                        depth={0}
                        activeSessionId={activeSessionId}
                        expandedSessionIds={expandedSessionIds}
                        runningSessionIds={runningSessionIds}
                        searching={searching}
                        sessionSelectionDisabled={sessionSelectionDisabled}
                        onToggle={toggleSession}
                        onSelect={onSelectSession}
                        onDelete={onDeleteSession}
                      />
                    ))}
                    {group.sessions.length === 0 ? (
                      <div className="empty-workspace">还没有会话</div>
                    ) : null}
                  </div>
                ) : null}
              </section>
            );
          })}

          {groups.length === 0 ? (
            <div className="empty-sessions">没有匹配的项目或会话</div>
          ) : null}
        </div>
      </section>

      <footer className="sidebar-footer">
        <button
          className="settings-button"
          type="button"
          disabled={settingsDisabled}
          onClick={onOpenSettings}
        >
          <span className="gear" aria-hidden="true" />
          <span>设置</span>
        </button>
      </footer>
    </aside>
  );
});
