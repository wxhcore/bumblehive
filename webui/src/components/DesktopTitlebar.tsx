import { startWindowDrag } from "../lib/platform";
import { Icon } from "./Icon";
import { Tooltip } from "./Tooltip";

export function DesktopTitlebar({ title, collapsed, onToggleSidebar, nativeDrag, hideSidebarToggle = false }: {
  title: string; collapsed: boolean; onToggleSidebar: () => void; nativeDrag: boolean; hideSidebarToggle?: boolean;
}) {
  return <header className="desktop-titlebar">
    <div className="titlebar-controls">
      {!hideSidebarToggle && <Tooltip label={collapsed ? "展开侧栏" : "折叠侧栏"}><button type="button" className="titlebar-button" aria-label={collapsed ? "展开侧栏" : "折叠侧栏"} aria-expanded={!collapsed} aria-controls="projectSidebar" onClick={onToggleSidebar}><Icon name="panel" /></button></Tooltip>}
    </div>
    <div className="titlebar-drag-region" data-tauri-drag-region={nativeDrag || undefined} onPointerDown={(event) => { if (nativeDrag && event.button === 0) startWindowDrag(); }}>
      {!hideSidebarToggle && <Icon className="desktop-titlebar-icon" name="folder" />}
      <span className="desktop-titlebar-title">{title}</span>
    </div>
  </header>;
}
