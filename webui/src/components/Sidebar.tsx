import { memo, useEffect, useMemo, useRef, useState } from "react";
import { workspaceKey, type KnownWorkspace } from "../lib/workspaces";
import type { SessionSummary } from "../types/api";
import { buildWorkspaceGroups } from "./sidebar/session-tree";
import type { PendingSession } from "./sidebar/types";
import { Icon } from "./Icon";
import { WorkspaceSection } from "./sidebar/WorkspaceSection";

export type { PendingSession } from "./sidebar/types";

interface SidebarProps {
  workspaces: KnownWorkspace[];
  sessions: SessionSummary[];
  activeSessionId: string | null;
  currentWorkspace: string | null;
  pendingSessions: PendingSession[];
  runningSessionIds: ReadonlySet<string>;
  backgroundSessionIds: ReadonlySet<string>;
  disabled: boolean;
  visible: boolean;
  searchOpen: boolean;
  onSearchOpenChange: (open: boolean) => void;
  sessionSelectionDisabled: boolean;
  onNewChat: () => void;
  onAddWorkspace: () => void;
  onNewChatInWorkspace: (workspace: string) => void;
  onRemoveWorkspace: (workspace: string) => void;
  onSelectSession: (sessionId: string) => void;
  onDeleteSession: (sessionId: string) => void;
}

export const Sidebar = memo(function Sidebar({
  workspaces,
  sessions,
  activeSessionId,
  currentWorkspace,
  pendingSessions,
  runningSessionIds,
  backgroundSessionIds,
  disabled,
  visible,
  searchOpen,
  onSearchOpenChange,
  sessionSelectionDisabled,
  onNewChat,
  onAddWorkspace,
  onNewChatInWorkspace,
  onRemoveWorkspace,
  onSelectSession,
  onDeleteSession,
}: SidebarProps) {
  const searchRef = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState("");
  const [collapsedWorkspaces, setCollapsedWorkspaces] = useState<
    ReadonlySet<string>
  >(() => new Set());
  const [expandedSessionIds, setExpandedSessionIds] = useState<
    ReadonlySet<string>
  >(() => new Set());
  useEffect(() => {
    if (searchOpen && visible) searchRef.current?.focus();
    if (!searchOpen) setQuery("");
  }, [searchOpen, visible]);

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

  useEffect(() => {
    if (!activeSessionId) return;
    const parents = new Map([
      ...sessions.map((session) => [session.session_id, session.parent_session_id] as const),
      ...pendingSessions.map((session) => [session.sessionId, session.parentSessionId] as const),
    ]);
    const ancestors = new Set<string>();
    let id = parents.get(activeSessionId);
    while (id && id !== activeSessionId && !ancestors.has(id)) {
      ancestors.add(id);
      id = parents.get(id);
    }
    if (ancestors.size) setExpandedSessionIds((current) => new Set([...current, ...ancestors]));
    setCollapsedWorkspaces((current) => {
      if (!current.has(workspaceKey(currentWorkspace))) return current;
      const next = new Set(current); next.delete(workspaceKey(currentWorkspace)); return next;
    });
    // Expand the selected path on navigation, not on every streamed list update.
  }, [activeSessionId]);

  const groups = useMemo(
    () => buildWorkspaceGroups(workspaces, sessions, pendingSessions, query),
    [pendingSessions, query, sessions, workspaces],
  );

  function toggleWorkspace(key: string) {
    if (query.trim()) return;
    setCollapsedWorkspaces((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  function toggleSession(sessionId: string) {
    if (query.trim()) return;
    setExpandedSessionIds((current) => {
      const next = new Set(current);
      if (next.has(sessionId)) next.delete(sessionId);
      else next.add(sessionId);
      return next;
    });
  }

  const searching = Boolean(query.trim());
  const blockingSessionIds = new Set([...runningSessionIds].filter((id) => !backgroundSessionIds.has(id)));

  return (
    <aside className="sidebar" id="projectSidebar" aria-label="项目与会话">
      <div className="brand" aria-label="BumbleHive">
        <img
          className="brand-lockup"
          src="/brand/bumblehive-wordmark.png"
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
          <Icon name="compose" />
          <span>新聊天</span>
        </button>
      </nav>

      {searchOpen && <div className="session-search-field">
        <input ref={searchRef} className="session-search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索项目或会话" aria-label="搜索项目或会话" onKeyDown={(event) => {
          if (event.key === "Escape") {
            event.stopPropagation();
            if (query) setQuery("");
            else onSearchOpenChange(false);
          }
        }} />
        {query && <button className="search-clear" type="button" aria-label="清空搜索" onClick={() => { setQuery(""); searchRef.current?.focus(); }}><Icon name="close" /></button>}
      </div>}

      <section className="project-tree" aria-labelledby="projectTitle">
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
                blockingSessionIds={blockingSessionIds}
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

    </aside>
  );
});
