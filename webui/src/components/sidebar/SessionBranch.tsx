import { branchIsRunning } from "./session-tree";
import type { SidebarSession } from "./types";

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

export function SessionBranch({
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
    hasChildren && (searching || expandedSessionIds.has(session.id));
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
