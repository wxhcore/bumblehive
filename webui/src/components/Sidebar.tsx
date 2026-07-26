import { memo, useMemo, useState } from "react";
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
  title: string;
  searchableText: string;
  createdAt: number;
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
        title,
        searchableText: `${title} ${session.last_message}`,
        createdAt,
      });
    }
    for (const pending of pendingSessions) {
      if (persistedIds.has(pending.sessionId)) continue;
      if (!visibleWorkspaceKeys.has(workspaceKey(pending.workspace))) continue;
      groupFor(pending.workspace).sessions.push({
        id: pending.sessionId,
        title: pending.title,
        searchableText: pending.title,
        createdAt: Number.POSITIVE_INFINITY,
      });
    }

    const normalizedQuery = query.trim().toLocaleLowerCase();
    const result = [...byWorkspace.values()]
      .sort(
        (left, right) =>
          compareCreatedAt(left.createdAt, right.createdAt) ||
          left.label.localeCompare(right.label),
      )
      .map((group) => ({
        ...group,
        sessions: [...group.sessions].sort(
          (left, right) =>
            compareCreatedAt(right.createdAt, left.createdAt) ||
            left.id.localeCompare(right.id),
        ),
      }));
    if (!normalizedQuery) return result;
    return result.flatMap((group) => {
      const workspaceMatches =
        includesQuery(group.label, normalizedQuery) ||
        includesQuery(group.path, normalizedQuery);
      const matchingSessions = workspaceMatches
        ? group.sessions
        : group.sessions.filter((session) =>
            includesQuery(session.searchableText, normalizedQuery),
          );
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
              runningSessionIds.has(session.id),
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
                      <div className="conversation-row" key={session.id}>
                        <button
                          className={`conversation${
                            session.id === activeSessionId ? " active" : ""
                          }${
                            runningSessionIds.has(session.id) ? " running" : ""
                          }`}
                          type="button"
                          disabled={sessionSelectionDisabled}
                          onClick={() => onSelectSession(session.id)}
                          title={session.title}
                        >
                          {session.title}
                        </button>
                        <button
                          className="session-delete"
                          type="button"
                          disabled={
                            sessionSelectionDisabled ||
                            runningSessionIds.has(session.id)
                          }
                          aria-label={`删除${session.title}`}
                          onClick={() => onDeleteSession(session.id)}
                        >
                          ×
                        </button>
                      </div>
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
