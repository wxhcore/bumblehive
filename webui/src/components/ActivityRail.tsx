import { Icon } from "./Icon";
import { Tooltip } from "./Tooltip";

interface ActivityRailProps {
  settingsOpen: boolean;
  sidebarCollapsed: boolean;
  disabled: boolean;
  onChat: () => void;
  onSearch: () => void;
  onSettings: () => void;
  onNewChat: () => void;
}

export function ActivityRail({ settingsOpen, sidebarCollapsed, disabled, onChat, onSearch, onSettings, onNewChat }: ActivityRailProps) {
  return <nav className="activity-rail" aria-label="应用导航">
    <Tooltip label="返回聊天"><button className="rail-button" type="button" aria-label="返回聊天" aria-current={!settingsOpen ? "page" : undefined} onClick={onChat}><Icon name="home" /></button></Tooltip>
    <Tooltip label="搜索项目或会话"><button className="rail-button" type="button" aria-label="搜索项目或会话" disabled={disabled} onClick={onSearch}><Icon name="search" /></button></Tooltip>
    <span className={`rail-new-chat${sidebarCollapsed ? " is-visible" : ""}`}><Tooltip label="新聊天"><button className="rail-button" type="button" aria-label="新聊天" disabled={disabled} onClick={onNewChat}><Icon name="compose" /></button></Tooltip></span>
    <div className="rail-bottom"><Tooltip label="设置"><button className="rail-button" type="button" aria-label="设置" aria-current={settingsOpen ? "page" : undefined} disabled={disabled} onClick={onSettings}><Icon name="settings" /></button></Tooltip></div>
  </nav>;
}
