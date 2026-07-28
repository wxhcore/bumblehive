import { memo, useEffect, useMemo, useRef, useState } from "react";
import { workspaceKey, type KnownWorkspace } from "../lib/workspaces";
import type { SessionSummary } from "../types/api";
import { buildWorkspaceGroups } from "./sidebar/session-tree";
import type { PendingSession } from "./sidebar/types";
import { WorkspaceSection } from "./sidebar/WorkspaceSection";

export type { PendingSession } from "./sidebar/types";

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

  const groups = useMemo(
    () => buildWorkspaceGroups(workspaces, sessions, pendingSessions, query),
    [pendingSessions, query, sessions, workspaces],
  );

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
            const selected = workspaceKey(currentWorkspace) === group.key;
            const expanded =
              searching || !collapsedWorkspaces.has(group.key);
            return (
              <WorkspaceSection
                key={group.key}
                group={group}
                selected={selected}
                expanded={expanded}
                searching={searching}
                disabled={disabled}
                sessionSelectionDisabled={sessionSelectionDisabled}
                activeSessionId={activeSessionId}
                expandedSessionIds={expandedSessionIds}
                runningSessionIds={runningSessionIds}
                onToggleWorkspace={toggleWorkspace}
                onToggleSession={toggleSession}
                onNewChat={onNewChatInWorkspace}
                onRemove={onRemoveWorkspace}
                onSelectSession={onSelectSession}
                onDeleteSession={onDeleteSession}
              />
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
