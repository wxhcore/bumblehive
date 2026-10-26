import { useEffect, useState } from "react";
import { getDesktopWindow, isWindowsDesktop, startWindowDrag } from "../lib/platform";
import { Icon } from "./Icon";
import { Tooltip } from "./Tooltip";

export function DesktopTitlebar({ title, collapsed, onToggleSidebar, nativeDrag, hideSidebarToggle = false }: {
  title: string; collapsed: boolean; onToggleSidebar: () => void; nativeDrag: boolean; hideSidebarToggle?: boolean;
}) {
  const [maximized, setMaximized] = useState(false);
  useEffect(() => {
    if (!isWindowsDesktop) return;
    const appWindow = getDesktopWindow();
    if (!appWindow) return;
    let disposed = false;
    let unlisten: (() => void) | undefined;
    const sync = () => {
      void appWindow.isMaximized().then((value) => {
        if (!disposed) setMaximized(value);
      }).catch(console.error);
    };
    void appWindow.onResized(sync).then((stop) => {
      if (disposed) stop();
      else { unlisten = stop; sync(); }
    }).catch(console.error);
    return () => { disposed = true; unlisten?.(); };
  }, []);
  const windowAction = (action: "minimize" | "toggleMaximize" | "close") => {
    void getDesktopWindow()?.[action]().catch(console.error);
  };
  return <header className="desktop-titlebar">
    <div className="titlebar-controls" data-tauri-drag-region={isWindowsDesktop || undefined}>
      {!hideSidebarToggle && <Tooltip label={collapsed ? "展开侧栏" : "折叠侧栏"}><button type="button" className="titlebar-button" aria-label={collapsed ? "展开侧栏" : "折叠侧栏"} aria-expanded={!collapsed} aria-controls="projectSidebar" onClick={onToggleSidebar}><Icon name="panel" /></button></Tooltip>}
    </div>
    <div className="titlebar-drag-region" data-tauri-drag-region={nativeDrag || isWindowsDesktop || undefined} onPointerDown={(event) => { if (nativeDrag && event.button === 0) startWindowDrag(); }}>
      {!hideSidebarToggle && <Icon className="desktop-titlebar-icon" name="folder" />}
      <span className="desktop-titlebar-title">{title}</span>
    </div>
    {isWindowsDesktop && <div className="window-caption-controls">
      <button type="button" className="window-caption-button" aria-label="最小化" title="最小化" onClick={() => windowAction("minimize")}>
        <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true"><path d="M1 6.5h10" /></svg>
      </button>
      <button type="button" className="window-caption-button" aria-label={maximized ? "向下还原" : "最大化"} title={maximized ? "向下还原" : "最大化"} onClick={() => windowAction("toggleMaximize")}>
        <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">{maximized ? <path d="M3.5 3.5v-2h7v7h-2m-7-5h7v7h-7z" /> : <rect x="1.5" y="1.5" width="9" height="9" />}</svg>
      </button>
      <button type="button" className="window-caption-button window-caption-close" aria-label="关闭窗口" title="关闭窗口" onClick={() => windowAction("close")}>
        <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true"><path d="m1.5 1.5 9 9m0-9-9 9" /></svg>
      </button>
    </div>}
  </header>;
}
