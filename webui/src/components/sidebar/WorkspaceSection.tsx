import { branchIsRunning } from "./session-tree";
import { SessionBranch } from "./SessionBranch";
import type { WorkspaceGroup } from "./types";

interface WorkspaceSectionProps {
  group: WorkspaceGroup;
  selected: boolean;
  expanded: boolean;
  searching: boolean;
  disabled: boolean;
  sessionSelectionDisabled: boolean;
  activeSessionId: string | null;
  expandedSessionIds: ReadonlySet<string>;
  runningSessionIds: ReadonlySet<string>;
  onToggleWorkspace: (workspaceKey: string) => void;
  onToggleSession: (sessionId: string) => void;
  onNewChat: (workspace: string) => void;
  onRemove: (workspace: string) => void;
  onSelectSession: (sessionId: string) => void;
  onDeleteSession: (sessionId: string) => void;
}

export function WorkspaceSection({
  group,
  selected,
  expanded,
  searching,
  disabled,
  sessionSelectionDisabled,
  activeSessionId,
  expandedSessionIds,
  runningSessionIds,
  onToggleWorkspace,
  onToggleSession,
  onNewChat,
  onRemove,
  onSelectSession,
  onDeleteSession,
}: WorkspaceSectionProps) {
  const workspaceRunning = group.sessions.some((session) =>
    branchIsRunning(session, runningSessionIds),
  );

  return (
    <section
      className="workspace-group"
      aria-label={group.label}
    >
      <div className="workspace-heading-row">
        <button
          className="workspace-heading"
          type="button"
          title={group.path || group.label}
          aria-expanded={expanded}
          aria-current={selected ? "true" : undefined}
          onClick={() => onToggleWorkspace(group.key)}
        >
          <span className="sidebar-folder-icon" aria-hidden="true" />
          <span className="workspace-heading-label">{group.label}</span>
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
            onClick={() => onRemove(group.path)}
          >
            ×
          </button>
          <button
            className="workspace-action workspace-add-session"
            type="button"
            disabled={disabled}
            aria-label={`在 ${group.label} 中新建会话`}
            title="新建会话"
            onClick={() => onNewChat(group.path)}
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
              onToggle={onToggleSession}
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
}
