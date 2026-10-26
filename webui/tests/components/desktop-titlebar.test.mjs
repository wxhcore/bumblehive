import assert from "node:assert/strict";
import { test } from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { server } from "../helpers/vite.mjs";

test("custom window buttons appear only in the Windows desktop app", async () => {
  const previousWindow = globalThis.window;
  const previousNavigator = Object.getOwnPropertyDescriptor(globalThis, "navigator");
  try {
    for (const [platform, desktop, expected] of [
      ["Win32", true, true],
      ["MacIntel", true, false],
      ["Win32", false, false],
    ]) {
      globalThis.window = desktop ? { __TAURI_INTERNALS__: {} } : {};
      Object.defineProperty(globalThis, "navigator", {
        configurable: true,
        value: { platform, userAgent: platform },
      });
      server.moduleGraph.invalidateAll();
      const { DesktopTitlebar } = await server.ssrLoadModule("/src/components/DesktopTitlebar.tsx");
      const html = renderToStaticMarkup(createElement(DesktopTitlebar, {
        title: "Example",
        collapsed: false,
        nativeDrag: platform === "MacIntel" && desktop,
        onToggleSidebar() {},
      }));
      for (const label of ["最小化", "最大化", "关闭窗口"]) {
        assert.equal(html.includes(`aria-label="${label}"`), expected, `${platform}, desktop=${desktop}: ${label}`);
      }
      assert.ok(html.includes("Example"));
    }
  } finally {
    if (previousWindow === undefined) delete globalThis.window;
    else globalThis.window = previousWindow;
    if (previousNavigator) Object.defineProperty(globalThis, "navigator", previousNavigator);
    else delete globalThis.navigator;
  }
});
