import { startWindowDrag } from "../lib/platform";

export function DesktopTitlebar({ title }: { title: string }) {
  return (
    <div
      className="desktop-titlebar"
      data-tauri-drag-region
      aria-hidden="true"
      onPointerDown={(event) => {
        if (event.button === 0) startWindowDrag();
      }}
    >
      <div className="desktop-titlebar-sidebar" />
      <div className="desktop-titlebar-divider" />
      <div className="desktop-titlebar-main">
        <span className="titlebar-folder-icon" />
        <span className="desktop-titlebar-title">{title}</span>
      </div>
    </div>
  );
}
