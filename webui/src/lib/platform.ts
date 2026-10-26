interface TauriWindowHandle {
  startDragging: () => Promise<void>;
  minimize: () => Promise<void>;
  toggleMaximize: () => Promise<void>;
  close: () => Promise<void>;
  isMaximized: () => Promise<boolean>;
  onResized: (handler: () => void) => Promise<() => void>;
}

interface TauriInternals {
  invoke: <T>(
    command: string,
    args?: Record<string, unknown>,
  ) => Promise<T>;
}

declare global {
  interface Window {
    __TAURI__?: {
      window?: {
        getCurrentWindow?: () => TauriWindowHandle;
      };
    };
    __TAURI_INTERNALS__?: TauriInternals;
  }
}

export const isMacOS = typeof navigator !== "undefined" && /Mac|iPhone|iPad|iPod/.test(
  `${navigator.platform} ${navigator.userAgent}`,
);

export const isMacDesktop =
  isMacOS && typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;

export const isWindowsDesktop =
  typeof navigator !== "undefined" && /Win/.test(navigator.platform) &&
  typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;

export function getDesktopWindow(): TauriWindowHandle | undefined {
  return window.__TAURI__?.window?.getCurrentWindow?.();
}

export function startWindowDrag(): void {
  const currentWindow = window.__TAURI__?.window?.getCurrentWindow?.();
  if (!currentWindow) return;
  void currentWindow.startDragging().catch(() => {
    // The data-tauri-drag-region attribute remains the native fallback.
  });
}

export async function confirmAction(message: string): Promise<boolean> {
  const invoke = window.__TAURI_INTERNALS__?.invoke;
  try {
    if (!invoke) return await window.confirm(message);
    const result = await invoke<string>("plugin:dialog|message", {
      title: "BumbleHive",
      message,
      kind: "warning",
      buttons: "OkCancel",
    });
    return result === "Ok";
  } catch {
    return false;
  }
}

export async function pickWorkspaceDirectory(): Promise<
  string | null | undefined
> {
  const invoke = window.__TAURI_INTERNALS__?.invoke;
  if (!invoke) return undefined;

  const selected = await invoke<string | string[] | null>(
    "plugin:dialog|open",
    {
      options: {
        title: "选择工作空间",
        directory: true,
        multiple: false,
        canCreateDirectories: true,
      },
    },
  );
  return Array.isArray(selected) ? (selected[0] ?? null) : selected;
}
