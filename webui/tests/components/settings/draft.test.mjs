import assert from "node:assert/strict";
import { before, test } from "node:test";
import { server } from "../../helpers/vite.mjs";

let settingsDraft;

before(async () => {
  settingsDraft = await server.ssrLoadModule("/src/components/settings/draft.ts");
});

test("settings draft maps UI fields back to the complete config shape", () => {
  const draft = settingsDraft.settingsToDraft(
    {
      provider: {
        type: "openai_chat_completions",
        model: "test-model",
        api_key_configured: false,
      },
      generation: {},
      agent: {
        instructions: "Be concise",
        dynamic_context: { project: "bumblehive" },
        skill_names: ["review"],
        tool_names: [],
      },
      runtime: {
        workspace: "/tmp/project",
      },
      mcp_servers: [
        {
          name: "docs",
          url: "https://mcp.example.test",
          headers: { Authorization: "" },
        },
      ],
    },
    "Asia/Shanghai",
  );
  assert.equal(draft.generation.maxCompletionTokens, 16_384);
  assert.equal(draft.runtime.workspace, "/tmp/project");
  assert.equal(draft.runtime.timezone, "Asia/Shanghai");
  assert.equal(draft.runtime.contextWindowTokens, 200_000);
  assert.equal(draft.runtime.maxToolResultChars, 20_000);
  assert.equal(draft.runtime.maxIterations, 300);
  draft.generation.thinkingEnabled = false;
  draft.generation.reasoningEffort = "vendor-ultra";

  const update = settingsDraft.draftToUpdate(draft, "temporary-secret");

  assert.equal(update.provider.api_key, "temporary-secret");
  assert.deepEqual(update.agent.dynamic_context, {
    project: "bumblehive",
  });
  assert.deepEqual(update.agent.skill_names, ["review"]);
  assert.deepEqual(update.agent.tool_names, []);
  assert.deepEqual(update.generation.extra_body, {
    thinking: { type: "disabled" },
  });
  assert.equal(update.generation.reasoning_effort, null);
  assert.equal(update.generation.max_completion_tokens, 16_384);
  assert.equal(update.runtime.context_window_tokens, 200_000);
  assert.equal(update.runtime.max_tool_result_chars, 20_000);
  assert.equal(update.runtime.max_iterations, 300);
  assert.equal(update.runtime.workspace, "/tmp/project");
  assert.equal(update.runtime.timezone, "Asia/Shanghai");
  assert.deepEqual(update.mcp_servers, [
    {
      name: "docs",
      url: "https://mcp.example.test",
      headers: { Authorization: "" },
    },
  ]);
});

test("configured timezone takes priority over the detected system timezone", () => {
  const draft = settingsDraft.settingsToDraft(
    {
      provider: {
        type: "openai_chat_completions",
        model: "test-model",
        api_key_configured: false,
      },
      generation: {},
      agent: {
        dynamic_context: {},
        skill_names: null,
        tool_names: null,
      },
      runtime: {
        timezone: "Europe/Paris",
      },
      mcp_servers: [],
    },
    "Asia/Shanghai",
  );

  assert.equal(draft.runtime.timezone, "Europe/Paris");
});

test("settings draft switches disabled thinking to a custom reasoning effort", () => {
  const draft = settingsDraft.settingsToDraft({
    provider: {
      type: "openai_chat_completions",
      model: "test-model",
      api_key_configured: false,
    },
    generation: {
      reasoning_effort: null,
      extra_body: {
        top_k: 20,
        thinking: { type: "disabled" },
      },
    },
    agent: {
      dynamic_context: {},
      skill_names: null,
      tool_names: null,
    },
    runtime: {},
    mcp_servers: [],
  });

  assert.equal(draft.generation.thinkingEnabled, false);
  assert.equal(draft.generation.reasoningEffort, "");

  draft.generation.thinkingEnabled = true;
  draft.generation.reasoningEffort = "vendor-ultra";
  const update = settingsDraft.draftToUpdate(draft, "");

  assert.equal(Object.hasOwn(update.provider, "api_key"), false);
  assert.equal(update.generation.reasoning_effort, "vendor-ultra");
  assert.equal(update.generation.extra_body, null);
});
