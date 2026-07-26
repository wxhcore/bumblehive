export const DEFAULT_WORKSPACE_KEY = "__bumblehive_default_workspace__";
export const WORKSPACE_REGISTRY_STORAGE_KEY =
  "bumblehive.workspace-registry.v1";
export const SELECTED_WORKSPACE_STORAGE_KEY =
  "bumblehive.selected-workspace.v1";

export interface KnownWorkspace {
  path: string;
  createdAt: number;
}

export interface WorkspaceRegistry {
  items: KnownWorkspace[];
  removedKeys: string[];
}

export function workspaceKey(path: string | null | undefined): string {
  return path?.trim() || DEFAULT_WORKSPACE_KEY;
}

export function workspaceLabel(path: string | null | undefined): string {
  if (!path?.trim()) return "默认工作区";
  const parts = path.split(/[\\/]/).filter(Boolean);
  return parts.at(-1) || path;
}

export function readWorkspaceRegistry(): WorkspaceRegistry {
  try {
    const raw = window.localStorage.getItem(WORKSPACE_REGISTRY_STORAGE_KEY);
    if (!raw) return { items: [], removedKeys: [] };
    const parsed = JSON.parse(raw) as Partial<WorkspaceRegistry>;
    const items = Array.isArray(parsed.items)
      ? parsed.items.flatMap((item) => {
          if (
            !item ||
            typeof item.path !== "string" ||
            !item.path.trim() ||
            typeof item.createdAt !== "number" ||
            !Number.isFinite(item.createdAt)
          ) {
            return [];
          }
          return [{ path: item.path.trim(), createdAt: item.createdAt }];
        })
      : [];
    const removedKeys = Array.isArray(parsed.removedKeys)
      ? parsed.removedKeys.filter(
          (key): key is string => typeof key === "string" && Boolean(key),
        )
      : [];
    return { items: sortWorkspaces(items), removedKeys };
  } catch {
    return { items: [], removedKeys: [] };
  }
}

export function writeWorkspaceRegistry(registry: WorkspaceRegistry): void {
  window.localStorage.setItem(
    WORKSPACE_REGISTRY_STORAGE_KEY,
    JSON.stringify(registry),
  );
}

export function readSelectedWorkspace(): string | null {
  const workspace = window.localStorage
    .getItem(SELECTED_WORKSPACE_STORAGE_KEY)
    ?.trim();
  return workspace || null;
}

export function writeSelectedWorkspace(workspace: string | null): void {
  if (workspace?.trim()) {
    window.localStorage.setItem(
      SELECTED_WORKSPACE_STORAGE_KEY,
      workspace.trim(),
    );
  } else {
    window.localStorage.removeItem(SELECTED_WORKSPACE_STORAGE_KEY);
  }
}

export function mergeDiscoveredWorkspaces(
  registry: WorkspaceRegistry,
  candidates: KnownWorkspace[],
  restore = false,
): WorkspaceRegistry {
  const removed = new Set(registry.removedKeys);
  const byKey = new Map(
    registry.items.map((workspace) => [
      workspaceKey(workspace.path),
      workspace,
    ]),
  );
  for (const candidate of candidates) {
    const path = candidate.path.trim();
    if (!path) continue;
    const key = workspaceKey(path);
    if (removed.has(key) && !restore) continue;
    if (restore) removed.delete(key);
    const existing = byKey.get(key);
    if (existing) {
      byKey.set(key, {
        ...existing,
        createdAt: Math.min(existing.createdAt, candidate.createdAt),
      });
    } else {
      byKey.set(key, { path, createdAt: candidate.createdAt });
    }
  }
  return {
    items: sortWorkspaces([...byKey.values()]),
    removedKeys: [...removed],
  };
}

export function removeKnownWorkspace(
  registry: WorkspaceRegistry,
  path: string,
): WorkspaceRegistry {
  const key = workspaceKey(path);
  return {
    items: registry.items.filter(
      (workspace) => workspaceKey(workspace.path) !== key,
    ),
    removedKeys: Array.from(new Set([...registry.removedKeys, key])),
  };
}

function sortWorkspaces(workspaces: KnownWorkspace[]): KnownWorkspace[] {
  return [...workspaces].sort(
    (left, right) =>
      left.createdAt - right.createdAt ||
      workspaceLabel(left.path).localeCompare(workspaceLabel(right.path)),
  );
}
