import assert from "node:assert/strict";
import { before, test } from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { server } from "../helpers/vite.mjs";

let settingsView;

before(async () => {
  settingsView = await server.ssrLoadModule("/src/components/SettingsView.tsx");
});

test("settings editor exposes context navigation and every config domain", () => {
  const html = renderToStaticMarkup(
    createElement(settingsView.SettingsView, {
      settings: {
        provider: {
          type: "openai_chat_completions",
          model: "test-model",
          base_url: "https://example.test/v1",
          api_key_configured: true,
        },
        generation: {},
        agent: {
          instructions: null,
          dynamic_context: {},
          skill_names: null,
          tool_names: null,
        },
        runtime: {
          workspace: "/tmp/project",
        },
        mcp_servers: [],
      },
      mode: "settings",
      hasRunningSessions: false,
      onCancel() {},
      async onSave(settings) {
        return settings;
      },
    }),
  );

  assert.match(html, />上下文</);
  assert.doesNotMatch(html, />Agent</);
  assert.match(html, />工具</);
  assert.match(html, />技能</);
  assert.doesNotMatch(html, />技能与工具</);
  assert.match(html, />运行环境</);
  assert.doesNotMatch(html, /<span>MCP 服务<\/span>/);
  assert.doesNotMatch(html, />高级</);
  assert.doesNotMatch(html, />Extra Body</);
  assert.doesNotMatch(html, /BumbleHive/);
  assert.match(html, /aria-haspopup="dialog"/);
  assert.match(html, /role="switch"/);
  assert.match(html, /aria-label="思考模式"/);
  assert.doesNotMatch(html, />开启思考</);
  assert.doesNotMatch(html, />关闭思考</);
  assert.match(html, /aria-label="推理强度"/);
  assert.doesNotMatch(html, /<option value="low">/);
  assert.doesNotMatch(html, />工具超时/);
  assert.doesNotMatch(html, />启用工具/);
});

test("initial setup exposes only the required model connection", () => {
  const html = renderToStaticMarkup(
    createElement(settingsView.SettingsView, {
      settings: {
        provider: {
          type: "openai_chat_completions",
          model: null,
          base_url: null,
          api_key_configured: false,
        },
        generation: {},
        agent: {
          instructions: null,
          dynamic_context: {},
          skill_names: null,
          tool_names: null,
        },
        runtime: {
          workspace: "/tmp/project",
        },
        mcp_servers: [],
      },
      mode: "setup",
      hasRunningSessions: false,
      onCancel() {},
      async onSave(settings) {
        return settings;
      },
    }),
  );

  assert.match(html, />连接模型</);
  assert.match(html, />保存并开始</);
  assert.match(html, />Base URL</);
  assert.match(html, />API Key</);
  assert.match(html, />模型</);
  assert.match(html, />所有更改已保存</);
  assert.doesNotMatch(html, />有尚未保存的更改</);
  assert.doesNotMatch(html, />所有设置</);
  assert.doesNotMatch(html, />上下文</);
  assert.doesNotMatch(html, />生成参数</);
  assert.doesNotMatch(html, />放弃更改</);
});
