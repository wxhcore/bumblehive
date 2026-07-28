export interface PendingSession {
  sessionId: string;
  workspace: string;
  title: string;
  parentSessionId?: string;
}

export interface SidebarSession {
  id: string;
  parentId: string | null;
  title: string;
  searchableText: string;
  createdAt: number;
  children: SidebarSession[];
}

export interface WorkspaceGroup {
  key: string;
  path: string;
  label: string;
  createdAt: number;
  sessions: SidebarSession[];
}
