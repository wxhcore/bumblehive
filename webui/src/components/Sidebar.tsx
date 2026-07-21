import { useMemo, useState } from "react";
import type { SessionSummary } from "../types/api";

interface SidebarProps {
  sessions: SessionSummary[];
  activeSessionId: string | null;
  pendingSessions: Array<{ sessionId: string; title: string }>;
  runningSessionIds: ReadonlySet<string>;
  disabled: boolean;
  settingsDisabled: boolean;
  sessionSelectionDisabled: boolean;
  onNewChat: () => void;
  onSelectSession: (sessionId: string) => void;
  onDeleteSession: (sessionId: string) => void;
  onOpenSettings: () => void;
}

export function Sidebar({
  sessions,
  activeSessionId,
  pendingSessions,
  runningSessionIds,
  disabled,
  settingsDisabled,
  sessionSelectionDisabled,
  onNewChat,
  onSelectSession,
  onDeleteSession,
  onOpenSettings,
}: SidebarProps) {
  const [searchOpen, setSearchOpen] = useState(false);
  const [query, setQuery] = useState("");
  const visibleSessions = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase();
    if (!normalized) return sessions;
    return sessions.filter((session) =>
      (session.title || session.last_message || session.session_id)
        .toLocaleLowerCase()
        .includes(normalized),
    );
  }, [query, sessions]);

  const persistedIds = new Set(sessions.map((session) => session.session_id));
  const unpersistedSessions = pendingSessions.filter(
    (session) => !persistedIds.has(session.sessionId),
  );

  return (
    <aside className="sidebar">
      <div className="brand" aria-label="BumbleHive">
        <span>BumbleHive</span>
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
          <span className="shortcut">⌘ N</span>
        </button>
        <button
          className="nav-button"
          type="button"
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
          placeholder="搜索最近会话"
          aria-label="搜索最近会话"
          autoFocus
        />
      ) : null}

      <section className="recent" aria-labelledby="recentTitle">
        <div className="section-label" id="recentTitle">
          最近会话
        </div>
        <div className="conversations">
          {unpersistedSessions.map((session) => (
            <button
              className={`conversation${
                session.sessionId === activeSessionId ? " active" : ""
              }${
                runningSessionIds.has(session.sessionId) ? " running" : ""
              }`}
              type="button"
              key={session.sessionId}
              disabled={sessionSelectionDisabled}
              onClick={() => onSelectSession(session.sessionId)}
              title={session.title}
            >
              {session.title}
            </button>
          ))}

          {visibleSessions.map((session) => (
            <div className="conversation-row" key={session.session_id}>
              <button
                className={`conversation${
                  session.session_id === activeSessionId ? " active" : ""
                }${
                  runningSessionIds.has(session.session_id) ? " running" : ""
                }`}
                type="button"
                disabled={sessionSelectionDisabled}
                onClick={() => onSelectSession(session.session_id)}
                title={session.last_message || session.title}
              >
                {session.title || session.last_message || "未命名会话"}
              </button>
              <button
                className="session-delete"
                type="button"
                disabled={
                  sessionSelectionDisabled ||
                  runningSessionIds.has(session.session_id)
                }
                aria-label={`删除${session.title || "会话"}`}
                onClick={() => onDeleteSession(session.session_id)}
              >
                ×
              </button>
            </div>
          ))}

          {unpersistedSessions.length === 0 && visibleSessions.length === 0 ? (
            <div className="empty-sessions">
              {query ? "没有匹配的会话" : "还没有会话"}
            </div>
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
}
