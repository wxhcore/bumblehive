import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type FormEvent,
} from "react";
import { createPortal } from "react-dom";
import {
  getModels,
  getSettingsOptions,
  refreshMcpServer,
  refreshMcpServers,
  testMcpServer,
} from "../api/http";
import { detectSystemTimeZone } from "../lib/default-settings";
import type {
  McpServerSettings,
  Settings,
  SettingsOptions,
  SettingsToolOption,
  SettingsUpdate,
} from "../types/api";
import {
  NullableNumberInput,
  SettingRow,
  SettingsSection,
  StringListEditor,
} from "./settings/controls";
import { SkillsSettings } from "./settings/SkillsSettings";
import {
  draftSignature,
  draftToUpdate,
  settingsToDraft,
  type SettingsDraft,
} from "./settings/draft";
import {
  buildToolSourceGroups,
  setToolsEnabled,
  toolIsEnabled,
  type ToolSourceGroup,
} from "./settings/tool-selection";

type SettingsPage =
  | "provider"
  | "context"
  | "tools"
  | "skills"
  | "runtime";

type ToolSettingsTab = "tools" | "mcp";

interface McpEditorState {
  index: number | null;
  server: McpServerSettings;
}

interface SettingsViewProps {
  settings: Settings;
  mode: "setup" | "settings";
  focusWorkspace?: boolean;
  hasRunningSessions: boolean;
  onCancel: () => void;
  onSave: (update: SettingsUpdate) => Promise<Settings>;
}

const NAV_ITEMS: Array<{
  id: SettingsPage;
  label: string;
  icon: string;
  keywords: string;
}> = [
  {
    id: "provider",
    label: "模型与服务商",
    icon: "✦",
    keywords: "模型 服务商 provider api key base url generation temperature token 推理",
  },
  {
    id: "context",
    label: "上下文",
    icon: "◎",
    keywords: "上下文 指令 instructions dynamic context prompt",
  },
  {
    id: "tools",
    label: "工具",
    icon: "◇",
    keywords: "工具 tools mcp 服务 server headers",
  },
  {
    id: "skills",
    label: "技能",
    icon: "✦",
    keywords: "技能 skills skill 导入 上传 删除 能力",
  },
  {
    id: "runtime",
    label: "运行环境",
    icon: "⌘",
    keywords: "运行 环境 workspace timezone context window 权限 路径",
  },
];

const EMPTY_OPTIONS: SettingsOptions = {
  skills: [],
  skill_errors: [],
  tools: [],
  mcp_statuses: [],
};

const PAGE_COPY: Record<SettingsPage, { title: string; description: string }> = {
  provider: {
    title: "模型与服务商",
    description: "配置模型连接，以及发送给模型的默认生成参数。",
  },
  context: {
    title: "上下文",
    description: "控制系统指令和每轮动态上下文的构建方式。",
  },
  tools: {
    title: "工具",
    description: "管理模型可以使用的工具，以及外部 MCP 工具来源。",
  },
  skills: {
    title: "技能",
    description: "导入和管理本地技能，并选择模型可以使用哪些技能。",
  },
  runtime: {
    title: "运行环境",
    description: "管理默认工作区、上下文预算和文件系统访问范围。",
  },
};

function updateMcpServer(
  servers: McpServerSettings[],
  index: number,
  update: Partial<McpServerSettings>,
): McpServerSettings[] {
  return servers.map((server, item) =>
    item === index ? { ...server, ...update } : server,
  );
}

function sameMcpServer(
  left: McpServerSettings | undefined,
  right: McpServerSettings | undefined,
): boolean {
  if (!left || !right) return false;
  const leftHeaders = Object.entries(left.headers).sort(([a], [b]) =>
    a.localeCompare(b),
  );
  const rightHeaders = Object.entries(right.headers).sort(([a], [b]) =>
    a.localeCompare(b),
  );
  return (
    left.name === right.name &&
    left.url === right.url &&
    JSON.stringify(leftHeaders) === JSON.stringify(rightHeaders)
  );
}

export function SettingsView({
  settings,
  mode,
  focusWorkspace = false,
  hasRunningSessions,
  onCancel,
  onSave,
}: SettingsViewProps) {
  const setupMode = mode === "setup";
  const canCancel = !setupMode;
  const [page, setPage] = useState<SettingsPage>(
    !setupMode && focusWorkspace ? "runtime" : "provider",
  );
  const systemTimeZone = useMemo(detectSystemTimeZone, []);
  const [query, setQuery] = useState("");
  const [toolTab, setToolTab] = useState<ToolSettingsTab>("tools");
  const [toolSource, setToolSource] = useState("all");
  const [toolSearch, setToolSearch] = useState("");
  const [mcpSearch, setMcpSearch] = useState("");
  const [mcpEditor, setMcpEditor] = useState<McpEditorState | null>(null);
  const [mcpEditorError, setMcpEditorError] = useState<string | null>(null);
  const [mcpTesting, setMcpTesting] = useState(false);
  const [mcpRefreshing, setMcpRefreshing] = useState<string | null>(null);
  const [draft, setDraft] = useState<SettingsDraft>(() =>
    settingsToDraft(settings, systemTimeZone),
  );
  const [apiKey, setApiKey] = useState("");
  const [options, setOptions] = useState<SettingsOptions>(EMPTY_OPTIONS);
  const [optionsError, setOptionsError] = useState<string | null>(null);
  const [modelOptions, setModelOptions] = useState<string[]>([]);
  const [modelPickerOpen, setModelPickerOpen] = useState(false);
  const [modelSearch, setModelSearch] = useState("");
  const [modelError, setModelError] = useState<string | null>(null);
  const [modelLoading, setModelLoading] = useState(false);
  const [modelPopoverStyle, setModelPopoverStyle] = useState<CSSProperties>({});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedMessage, setSavedMessage] = useState<string | null>(null);
  const baselineRef = useRef(
    draftSignature(settingsToDraft(settings, systemTimeZone), ""),
  );
  const modelRequestId = useRef(0);
  const modelTriggerRef = useRef<HTMLButtonElement>(null);
  const modelPopoverRef = useRef<HTMLDivElement>(null);
  const modelSearchRef = useRef<HTMLInputElement>(null);
  const selectedModelRef = useRef<HTMLButtonElement>(null);
  const settingsContentRef = useRef<HTMLFormElement>(null);

  useEffect(() => {
    const nextDraft = settingsToDraft(settings, systemTimeZone);
    setDraft(nextDraft);
    setApiKey("");
    setMcpEditor(null);
    setMcpEditorError(null);
    baselineRef.current = draftSignature(nextDraft, "");
  }, [settings, systemTimeZone]);

  useEffect(() => {
    if (setupMode) {
      setPage("provider");
    } else if (focusWorkspace) {
      setPage("runtime");
    }
  }, [focusWorkspace, setupMode]);

  useEffect(() => {
    if (page !== "provider") setModelPickerOpen(false);
  }, [page]);

  useEffect(() => {
    if (!mcpEditor) return;

    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape" && !mcpTesting) {
        setMcpEditor(null);
        setMcpEditorError(null);
      }
    }

    document.addEventListener("keydown", closeOnEscape);
    return () => document.removeEventListener("keydown", closeOnEscape);
  }, [mcpEditor, mcpTesting]);

  useLayoutEffect(() => {
    if (settingsContentRef.current) settingsContentRef.current.scrollTop = 0;
  }, [page]);

  useEffect(() => {
    modelRequestId.current += 1;
    setModelOptions([]);
    setModelError(null);
  }, [apiKey, draft.provider.baseUrl]);

  useLayoutEffect(() => {
    if (!modelPickerOpen) return;

    function positionPicker() {
      const trigger = modelTriggerRef.current;
      if (!trigger) return;
      const rect = trigger.getBoundingClientRect();
      const gutter = 12;
      const width = Math.min(
        Math.max(Math.min(rect.width, 400), 360),
        window.innerWidth - gutter * 2,
      );
      const estimatedHeight = Math.min(
        modelPopoverRef.current?.offsetHeight || 330,
        window.innerHeight - gutter * 2,
      );
      const left = Math.min(
        Math.max(gutter, rect.right - width),
        window.innerWidth - width - gutter,
      );
      const below = rect.bottom + 7;
      const top =
        below + estimatedHeight <= window.innerHeight - gutter
          ? below
          : Math.max(gutter, rect.top - estimatedHeight - 7);
      setModelPopoverStyle({ left, top, width });
    }

    positionPicker();
    window.addEventListener("resize", positionPicker);
    window.addEventListener("scroll", positionPicker, true);
    return () => {
      window.removeEventListener("resize", positionPicker);
      window.removeEventListener("scroll", positionPicker, true);
    };
  }, [modelLoading, modelOptions.length, modelPickerOpen]);

  useLayoutEffect(() => {
    if (!modelPickerOpen || modelSearch.trim()) return;

    const scrollFrame = window.requestAnimationFrame(() => {
      selectedModelRef.current?.scrollIntoView({ block: "nearest" });
    });
    return () => window.cancelAnimationFrame(scrollFrame);
  }, [
    draft.provider.model,
    modelOptions.length,
    modelPickerOpen,
    modelSearch,
  ]);

  useEffect(() => {
    if (!modelPickerOpen) return;

    const focusFrame = window.requestAnimationFrame(() => {
      modelSearchRef.current?.focus({ preventScroll: true });
    });

    function closeOnOutsidePointer(event: PointerEvent) {
      const target = event.target;
      if (!(target instanceof Node)) return;
      if (
        modelPopoverRef.current?.contains(target) ||
        modelTriggerRef.current?.contains(target)
      ) {
        return;
      }
      setModelPickerOpen(false);
    }

    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape") setModelPickerOpen(false);
    }

    document.addEventListener("pointerdown", closeOnOutsidePointer);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      window.cancelAnimationFrame(focusFrame);
      document.removeEventListener("pointerdown", closeOnOutsidePointer);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [modelPickerOpen]);

  useEffect(() => {
    if (setupMode) {
      setOptions(EMPTY_OPTIONS);
      setOptionsError(null);
      return;
    }
    let cancelled = false;
    setOptionsError(null);
    void getSettingsOptions()
      .then((result) => {
        if (!cancelled) setOptions(result);
      })
      .catch((reason) => {
        if (!cancelled) {
          setOptionsError(
            reason instanceof Error ? reason.message : "无法读取工具列表",
          );
        }
      });
    return () => {
      cancelled = true;
    };
  }, [settings, setupMode]);

  const signature = draftSignature(draft, apiKey);
  const dirty = signature !== baselineRef.current;
  const mcpConfigDirty =
    draft.mcpServers.length !== settings.mcp_servers.length ||
    draft.mcpServers.some(
      (server, index) => !sameMcpServer(server, settings.mcp_servers[index]),
    );
  const pageCopy = setupMode
    ? {
        title: "连接模型",
        description: "完成模型连接后，即可进入 BumbleHive 开始对话。",
      }
    : PAGE_COPY[page];
  const filteredNavItems = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) return NAV_ITEMS;
    return NAV_ITEMS.filter((item) =>
      `${item.label} ${item.keywords}`.toLowerCase().includes(normalized),
    );
  }, [query]);
  const toolGroups = useMemo(
    () =>
      buildToolSourceGroups(
        options.tools,
        draft.mcpServers,
        options.mcp_statuses,
      ),
    [draft.mcpServers, options.mcp_statuses, options.tools],
  );
  const activeToolGroup =
    toolSource === "all"
      ? null
      : toolGroups.find((group) => group.id === toolSource) ?? null;

  useEffect(() => {
    if (
      toolSource !== "all" &&
      !toolGroups.some((group) => group.id === toolSource)
    ) {
      setToolSource("all");
    }
  }, [toolGroups, toolSource]);

  const visibleModels = useMemo(() => {
    const normalized = modelSearch.trim().toLowerCase();
    if (!normalized) return modelOptions;
    return modelOptions.filter((item) =>
      item.toLowerCase().includes(normalized),
    );
  }, [modelOptions, modelSearch]);
  const manualModelCandidate = modelSearch.trim();
  const hasExactModel = modelOptions.some(
    (model) => model.toLowerCase() === manualModelCandidate.toLowerCase(),
  );
  const canFetchModels = Boolean(
    draft.provider.baseUrl.trim() &&
      (apiKey.trim() || settings.provider.api_key_configured),
  );

  const updateProvider = useCallback(
    (update: Partial<SettingsDraft["provider"]>) => {
      setDraft((current) => ({
        ...current,
        provider: { ...current.provider, ...update },
      }));
      setSavedMessage(null);
    },
    [],
  );

  const updateGeneration = useCallback(
    (update: Partial<SettingsDraft["generation"]>) => {
      setDraft((current) => ({
        ...current,
        generation: { ...current.generation, ...update },
      }));
      setSavedMessage(null);
    },
    [],
  );

  const updateContext = useCallback(
    (update: Partial<SettingsDraft["context"]>) => {
      setDraft((current) => ({
        ...current,
        context: { ...current.context, ...update },
      }));
      setSavedMessage(null);
    },
    [],
  );

  const updateRuntime = useCallback(
    (update: Partial<SettingsDraft["runtime"]>) => {
      setDraft((current) => ({
        ...current,
        runtime: { ...current.runtime, ...update },
      }));
      setSavedMessage(null);
    },
    [],
  );

  const loadModels = useCallback(async () => {
    const requestId = ++modelRequestId.current;
    setModelLoading(true);
    setModelError(null);
    try {
      const key = apiKey.trim();
      const response = await getModels({
        base_url: draft.provider.baseUrl.trim(),
        ...(key ? { api_key: key } : {}),
      });
      const nextModels = Array.from(
        new Set(response.models.map((item) => item.trim()).filter(Boolean)),
      );
      if (requestId !== modelRequestId.current) return;
      setModelOptions(nextModels);
    } catch (reason) {
      if (requestId !== modelRequestId.current) return;
      setModelOptions([]);
      setModelError(
        reason instanceof Error ? reason.message : "模型列表加载失败",
      );
    } finally {
      if (requestId === modelRequestId.current) setModelLoading(false);
    }
  }, [apiKey, draft.provider.baseUrl]);

  function openModelPicker() {
    const opening = !modelPickerOpen;
    setModelPickerOpen(opening);
    if (!opening) return;
    setModelSearch("");
    if (!modelOptions.length && !modelLoading && canFetchModels) {
      void loadModels();
    }
  }

  function chooseModel(model: string) {
    const value = model.trim();
    if (!value) return;
    updateProvider({ model: value });
    setModelSearch("");
    setModelPickerOpen(false);
  }

  function resetDraft() {
    const nextDraft = settingsToDraft(settings);
    setDraft(nextDraft);
    setApiKey("");
    setMcpEditor(null);
    setMcpEditorError(null);
    setError(null);
    setSavedMessage(null);
  }

  function requestClose() {
    if (dirty && !window.confirm("放弃尚未保存的设置更改？")) return;
    onCancel();
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSavedMessage(null);
    if (hasRunningSessions) {
      setError("有任务正在运行，请等待任务完成后再保存设置");
      return;
    }
    if (setupMode) {
      if (!draft.provider.baseUrl.trim()) {
        setError("请输入 Base URL");
        return;
      }
      if (!apiKey.trim() && !settings.provider.api_key_configured) {
        setError("请输入 API Key");
        return;
      }
      if (!draft.provider.model.trim()) {
        setError("请选择或输入模型");
        return;
      }
    }
    setSaving(true);
    try {
      const update = draftToUpdate(draft, apiKey);
      const saved = await onSave(update);
      const nextDraft = settingsToDraft(saved, systemTimeZone);
      setDraft(nextDraft);
      setApiKey("");
      baselineRef.current = draftSignature(settingsToDraft(saved), "");
      setSavedMessage("设置已保存");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "设置保存失败");
    } finally {
      setSaving(false);
    }
  }

  function setToolEnabled(
    targetNames: string[],
    enabled: boolean,
  ) {
    const availableNames = options.tools.map((tool) => tool.name);
    setDraft((current) => ({
      ...current,
      context: {
        ...current.context,
        toolNames: setToolsEnabled(
          current.context.toolNames,
          targetNames,
          enabled,
          availableNames,
        ),
      },
    }));
    setSavedMessage(null);
  }

  function openMcpEditor(index: number) {
    const server = draft.mcpServers[index];
    if (!server) return;
    setMcpEditor({
      index,
      server: {
        name: server.name,
        url: server.url,
        headers: { ...server.headers },
      },
    });
    setMcpEditorError(null);
  }

  function addMcpServer() {
    setMcpEditor({
      index: null,
      server: { name: "", url: "", headers: {} },
    });
    setMcpEditorError(null);
  }

  function updateMcpEditor(update: Partial<McpServerSettings>) {
    setMcpEditor((current) =>
      current
        ? {
            ...current,
            server: { ...current.server, ...update },
          }
        : current,
    );
    setMcpEditorError(null);
  }

  async function applyMcpEditor() {
    if (!mcpEditor) return;
    const editor = mcpEditor;
    const server = {
      name: editor.server.name.trim(),
      url: editor.server.url.trim(),
      headers: { ...editor.server.headers },
    };
    if (!server.name) {
      setMcpEditorError("请输入服务名称");
      return;
    }
    if (!server.url) {
      setMcpEditorError("请输入服务 URL");
      return;
    }
    if (
      draft.mcpServers.some(
        (item, index) =>
          index !== editor.index && item.name.trim() === server.name,
      )
    ) {
      setMcpEditorError("MCP 服务名称不能重复");
      return;
    }

    setMcpTesting(true);
    setMcpEditorError(null);
    try {
      const originalName =
        editor.index === null
          ? undefined
          : draft.mcpServers[editor.index]?.name.trim() || undefined;
      const result = await testMcpServer({
        server,
        ...(originalName ? { original_name: originalName } : {}),
      });
      setDraft((current) => ({
        ...current,
        mcpServers:
          editor.index === null
            ? [...current.mcpServers, server]
            : updateMcpServer(current.mcpServers, editor.index, server),
      }));
      setMcpEditor(null);
      setMcpEditorError(null);
      setSavedMessage(
        `连接成功，发现 ${result.registered_tools.length} 个工具；保存设置后生效`,
      );
    } catch (reason) {
      setMcpEditorError(
        reason instanceof Error ? reason.message : "MCP 连接测试失败",
      );
    } finally {
      setMcpTesting(false);
    }
  }

  async function reloadMcp(target?: string) {
    if (hasRunningSessions) {
      setOptionsError("有任务正在运行，请等待任务完成后再刷新 MCP 服务");
      return;
    }
    const refreshKey = target ?? "*";
    setMcpRefreshing(refreshKey);
    setOptionsError(null);
    try {
      const result = target
        ? await refreshMcpServer(target)
        : await refreshMcpServers();
      setOptions(result);
      const toolCount = target
        ? result.mcp_statuses.find((item) => item.name === target)
            ?.registered_tools.length ?? 0
        : result.tools.filter((tool) => tool.source === "mcp").length;
      setSavedMessage(
        target
          ? `${target} 已刷新，共 ${toolCount} 个工具`
          : `MCP 服务已全部刷新，共 ${toolCount} 个工具`,
      );
    } catch (reason) {
      setOptionsError(
        reason instanceof Error ? reason.message : "MCP 服务刷新失败",
      );
      try {
        setOptions(await getSettingsOptions());
      } catch {
        // Preserve the refresh error when status recovery also fails.
      }
    } finally {
      setMcpRefreshing(null);
    }
  }

  function deleteMcpServer() {
    if (!mcpEditor || mcpEditor.index === null) return;
    if (!window.confirm(`删除 MCP 服务“${mcpEditor.server.name}”？`)) return;
    const removedIndex = mcpEditor.index;
    setDraft((current) => ({
      ...current,
      mcpServers: current.mcpServers.filter(
        (_, index) => index !== removedIndex,
      ),
    }));
    setToolSource("all");
    setMcpEditor(null);
    setMcpEditorError(null);
    setSavedMessage(null);
  }

  function renderProviderPage() {
    return (
      <>
        <SettingsSection
          title="连接"
          description="当前通过 OpenAI Chat Completions 兼容协议访问模型。"
        >
          <SettingRow
            title="服务商类型"
            description="当前版本仅支持 OpenAI 兼容接口"
          >
            <select
              value={draft.provider.type}
              onChange={(event) => updateProvider({ type: event.target.value })}
            >
              <option value="openai_chat_completions">
                OpenAI Chat Completions
              </option>
            </select>
          </SettingRow>

          <SettingRow
            title="Base URL"
            description="服务商的 API 根地址"
          >
            <input
              type="url"
              value={draft.provider.baseUrl}
              placeholder="https://api.openai.com/v1"
              onChange={(event) => updateProvider({ baseUrl: event.target.value })}
            />
          </SettingRow>

          <SettingRow
            title="API Key"
            description={
              settings.provider.api_key_configured
                ? "已经安全配置，输入新值并保存即可替换"
                : "尚未配置"
            }
          >
            <input
              type="password"
              value={apiKey}
              autoComplete="off"
              placeholder={
                settings.provider.api_key_configured
                  ? "留空表示不修改"
                  : "输入 API Key"
              }
              onChange={(event) => {
                setApiKey(event.target.value);
                setSavedMessage(null);
              }}
            />
          </SettingRow>

          <SettingRow
            title="模型"
            description="选择服务商返回的模型，或手动输入 ID"
          >
            <div className="settings-model-field">
              <button
                ref={modelTriggerRef}
                className="settings-model-selector"
                type="button"
                aria-haspopup="dialog"
                aria-expanded={modelPickerOpen}
                onClick={openModelPicker}
              >
                <span className="settings-model-selector-copy">
                  <strong>
                    {draft.provider.model.trim() || "选择模型"}
                  </strong>
                </span>
                {modelLoading ? (
                  <span
                    className="settings-model-spinner"
                    aria-label="正在获取模型"
                  />
                ) : (
                  <span className="settings-model-chevron" aria-hidden="true" />
                )}
              </button>
              {modelError ? (
                <div
                  className="settings-field-note error"
                  role="alert"
                >
                  {modelError}
                </div>
              ) : null}
            </div>
          </SettingRow>
        </SettingsSection>

        {!setupMode ? (
          <SettingsSection
            title="生成参数"
            description="留空会使用内置值或模型服务商的默认值。"
          >
          <SettingRow
            title="最大输出 Token"
            description="默认 16,384；限制单次模型回复长度"
          >
            <NullableNumberInput
              value={draft.generation.maxCompletionTokens}
              placeholder="默认 16,384"
              min={1}
              step={1}
              ariaLabel="最大输出 Token"
              onChange={(maxCompletionTokens) =>
                updateGeneration({ maxCompletionTokens })
              }
            />
          </SettingRow>

          <SettingRow
            title="Temperature"
            description="数值越高，生成结果通常越随机"
          >
            <NullableNumberInput
              value={draft.generation.temperature}
              placeholder="服务商默认"
              min={0}
              step={0.1}
              ariaLabel="Temperature"
              onChange={(temperature) => updateGeneration({ temperature })}
            />
          </SettingRow>

          <SettingRow
            title="思考模式"
            description="关闭时发送 thinking.type=disabled"
          >
            <label className="settings-thinking-toggle">
              <span className="tool-toggle">
                <input
                  type="checkbox"
                  role="switch"
                  aria-label="思考模式"
                  checked={draft.generation.thinkingEnabled}
                  onChange={(event) =>
                    event.target.checked
                      ? updateGeneration({ thinkingEnabled: true })
                      : updateGeneration({
                          thinkingEnabled: false,
                          reasoningEffort: "",
                        })
                  }
                />
                <span aria-hidden="true" />
              </span>
            </label>
          </SettingRow>

          {draft.generation.thinkingEnabled ? (
            <SettingRow
              title="推理强度"
              description="按服务商要求填写 reasoning_effort；留空则不发送"
            >
              <input
                value={draft.generation.reasoningEffort}
                placeholder="例如 high、max 或服务商自定义值"
                aria-label="推理强度"
                onChange={(event) =>
                  updateGeneration({ reasoningEffort: event.target.value })
                }
              />
            </SettingRow>
          ) : null}
          </SettingsSection>
        ) : null}
      </>
    );
  }

  function renderContextPage() {
    return (
      <>
        <SettingsSection
          title="系统指令"
          description="为空时使用内置的默认系统指令。"
        >
          <SettingRow
            title="自定义指令"
            description="会替换内置系统指令，并注入每次模型请求"
            wide
          >
            <textarea
              className="settings-code-textarea settings-instructions"
              value={draft.context.instructions}
              placeholder="留空使用默认指令"
              onChange={(event) =>
                updateContext({ instructions: event.target.value })
              }
            />
          </SettingRow>
        </SettingsSection>

        <SettingsSection
          title="动态上下文"
          description="这些键值会作为运行时上下文附加到每一条用户消息。"
        >
          <SettingRow
            title="上下文数据"
            description='必须是 JSON 对象，例如 {"project":"bumblehive"}'
            wide
          >
            <textarea
              className="settings-code-textarea"
              value={draft.context.dynamicContextJson}
              spellCheck={false}
              onChange={(event) =>
                updateContext({ dynamicContextJson: event.target.value })
              }
            />
          </SettingRow>
        </SettingsSection>
      </>
    );
  }

  function renderToolRow(tool: SettingsToolOption) {
    const enabled = toolIsEnabled(draft.context.toolNames, tool.name);
    return (
      <label className="tool-browser-row" key={tool.name}>
        <span className="tool-browser-row-copy">
          <strong>{tool.name}</strong>
          <span title={tool.description}>
            {tool.description || "暂无描述"}
          </span>
        </span>
        <span className="tool-toggle">
          <input
            type="checkbox"
            checked={enabled}
            aria-label={`${enabled ? "关闭" : "开启"}工具 ${tool.name}`}
            onChange={() => setToolEnabled([tool.name], !enabled)}
          />
          <span aria-hidden="true" />
        </span>
      </label>
    );
  }

  function renderToolGroup(group: ToolSourceGroup, showHeading: boolean) {
    const normalizedSearch = toolSearch.trim().toLowerCase();
    const visibleTools = group.tools.filter((tool) =>
      `${tool.name} ${tool.description}`
        .toLowerCase()
        .includes(normalizedSearch),
    );
    if (!visibleTools.length) return null;

    return (
      <section className="tool-browser-group" key={group.id}>
        {showHeading ? (
          <div className="tool-browser-group-heading">
            <div>
              {group.kind === "mcp" ? (
                <span
                  className={`status-dot${
                    group.connected ? " connected" : ""
                  }`}
                />
              ) : null}
              <strong>{group.name}</strong>
            </div>
            <span>{group.tools.length} 个工具</span>
          </div>
        ) : null}
        <div className="tool-browser-rows">
          {visibleTools.map(renderToolRow)}
        </div>
      </section>
    );
  }

  function renderToolBrowser() {
    const selectedGroups = activeToolGroup ? [activeToolGroup] : toolGroups;
    const targetTools = activeToolGroup?.tools ?? options.tools;
    const targetNames = targetTools.map((tool) => tool.name);
    const allTargetToolsEnabled =
      targetNames.length > 0 &&
      targetNames.every((name) =>
        toolIsEnabled(draft.context.toolNames, name),
      );
    const enabledCount = targetNames.filter((name) =>
      toolIsEnabled(draft.context.toolNames, name),
    ).length;
    const normalizedSearch = toolSearch.trim().toLowerCase();
    const hasVisibleTools = selectedGroups.some((group) =>
      group.tools.some((tool) =>
        `${tool.name} ${tool.description}`
          .toLowerCase()
          .includes(normalizedSearch),
      ),
    );

    return (
      <div className="tool-browser">
        <aside className="tool-source-rail" aria-label="工具来源">
          <div className="tool-source-heading">工具来源</div>
          <button
            type="button"
            className={toolSource === "all" ? "active" : ""}
            onClick={() => setToolSource("all")}
          >
            <span className="tool-source-icon">⌘</span>
            <span>全部工具</span>
            <small>{options.tools.length}</small>
          </button>
          <button
            type="button"
            className={toolSource === "local" ? "active" : ""}
            onClick={() => setToolSource("local")}
          >
            <span className="tool-source-icon">◇</span>
            <span>内置工具</span>
            <small>{toolGroups[0]?.tools.length ?? 0}</small>
          </button>

          {toolGroups.some((group) => group.kind === "mcp") ? (
            <div className="tool-source-label">MCP 服务</div>
          ) : null}
          {toolGroups
            .filter((group) => group.kind === "mcp")
            .map((group) => (
              <button
                type="button"
                key={group.id}
                className={toolSource === group.id ? "active" : ""}
                onClick={() => setToolSource(group.id)}
              >
                <span
                  className={`status-dot${
                    group.connected ? " connected" : ""
                  }`}
                />
                <span title={group.name}>{group.name}</span>
                <small>{group.tools.length}</small>
              </button>
            ))}
        </aside>

        <section className="tool-browser-main">
          <header className="tool-browser-header">
            <div>
              <div className="tool-browser-title">
                {activeToolGroup?.name ?? "全部工具"}
              </div>
              <div className="tool-browser-subtitle">
                {activeToolGroup?.kind === "mcp"
                  ? activeToolGroup.connected
                    ? "服务已连接"
                    : "服务未连接"
                  : activeToolGroup
                    ? "BumbleHive 内置工具"
                    : "按工具来源分组显示"}
              </div>
            </div>
            <div className="tool-browser-actions">
              {activeToolGroup?.kind === "mcp" &&
              activeToolGroup.serverIndex !== null ? (
                <button
                  type="button"
                  onClick={() => {
                    setToolTab("mcp");
                    openMcpEditor(activeToolGroup.serverIndex as number);
                  }}
                >
                  管理服务
                  <span aria-hidden="true">›</span>
                </button>
              ) : null}
              <button
                type="button"
                disabled={!targetNames.length}
                onClick={() =>
                  setToolEnabled(targetNames, !allTargetToolsEnabled)
                }
              >
                {allTargetToolsEnabled ? "全部关闭" : "全部开启"}
              </button>
            </div>
          </header>

          <div className="tool-browser-scroll">
            {hasVisibleTools ? (
              selectedGroups.map((group) =>
                renderToolGroup(group, !activeToolGroup),
              )
            ) : (
              <div className="tool-browser-empty">
                <span aria-hidden="true">◇</span>
                <strong>
                  {toolSearch.trim()
                    ? "没有匹配的工具"
                    : activeToolGroup?.kind === "mcp" &&
                        !activeToolGroup.connected
                      ? "该 MCP 服务尚未连接"
                      : "当前没有可用工具"}
                </strong>
                <p>
                  {activeToolGroup?.kind === "mcp" &&
                  !activeToolGroup.connected
                    ? "请前往 MCP 分页检查连接配置。"
                    : "工具可用后会自动显示在这里。"}
                </p>
              </div>
            )}
          </div>

          <footer className="tool-browser-footer">
            <span>
              已启用 {enabledCount} / {targetNames.length} 个工具
            </span>
            {draft.context.toolNames === null ? (
              <span>新工具将自动启用</span>
            ) : null}
          </footer>
        </section>
      </div>
    );
  }

  function renderToolsPage() {
    const activeSearch = toolTab === "tools" ? toolSearch : mcpSearch;
    return (
      <div className="tool-page">
        <div className="tool-page-toolbar">
          <div className="tool-page-tabs" role="tablist" aria-label="工具设置">
            <button
              type="button"
              role="tab"
              aria-selected={toolTab === "tools"}
              className={toolTab === "tools" ? "active" : ""}
              onClick={() => setToolTab("tools")}
            >
              工具 <span>{options.tools.length}</span>
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={toolTab === "mcp"}
              className={toolTab === "mcp" ? "active" : ""}
              onClick={() => setToolTab("mcp")}
            >
              MCP <span>{draft.mcpServers.length}</span>
            </button>
          </div>

          <label className="tool-page-search">
            <span aria-hidden="true" />
            <input
              value={activeSearch}
              placeholder={toolTab === "tools" ? "搜索工具" : "搜索 MCP 服务"}
              aria-label={
                toolTab === "tools" ? "搜索工具" : "搜索 MCP 服务"
              }
              onChange={(event) =>
                toolTab === "tools"
                  ? setToolSearch(event.target.value)
                  : setMcpSearch(event.target.value)
              }
            />
          </label>
        </div>

        {optionsError ? (
          <div className="settings-page-alert" role="alert">
            无法读取当前工具列表：{optionsError}
          </div>
        ) : null}

        {toolTab === "tools" ? renderToolBrowser() : renderMcpPage()}
      </div>
    );
  }

  function renderRuntimePage() {
    return (
      <>
        <SettingsSection
          title="默认环境"
          description="每个会话可以拥有自己的工作区；这里设置的是未指定时的默认值。"
        >
          <SettingRow
            title="默认工作区"
            description="新建任务未选择项目时使用的目录"
            wide
          >
            <input
              value={draft.runtime.workspace}
              autoFocus={focusWorkspace}
              placeholder="~/.bumblehive/workspace"
              onChange={(event) =>
                updateRuntime({ workspace: event.target.value })
              }
            />
          </SettingRow>
          <SettingRow
            title="时区"
            description="未配置时自动读取系统 IANA 时区；保存后写入配置"
          >
            <input
              value={draft.runtime.timezone}
              placeholder="未能读取，可手动填写（例如 Asia/Shanghai）"
              onChange={(event) =>
                updateRuntime({ timezone: event.target.value })
              }
            />
          </SettingRow>
        </SettingsSection>

        <SettingsSection
          title="上下文预算"
          description="控制历史裁剪、工具结果长度和模型/工具循环上限。"
        >
          <SettingRow
            title="上下文窗口"
            description="默认 200,000 Token"
          >
            <NullableNumberInput
              value={draft.runtime.contextWindowTokens}
              placeholder="默认 200,000"
              min={1}
              step={1}
              ariaLabel="上下文窗口"
              onChange={(contextWindowTokens) =>
                updateRuntime({ contextWindowTokens })
              }
            />
          </SettingRow>
          <SettingRow
            title="工具结果字符上限"
            description="默认 20,000 字符"
          >
            <NullableNumberInput
              value={draft.runtime.maxToolResultChars}
              placeholder="默认 20,000"
              min={1}
              step={1}
              ariaLabel="工具结果字符上限"
              onChange={(maxToolResultChars) =>
                updateRuntime({ maxToolResultChars })
              }
            />
          </SettingRow>
          <SettingRow
            title="最大迭代次数"
            description="默认 300 次模型/工具循环"
          >
            <NullableNumberInput
              value={draft.runtime.maxIterations}
              placeholder="默认 300"
              min={1}
              step={1}
              ariaLabel="最大迭代次数"
              onChange={(maxIterations) => updateRuntime({ maxIterations })}
            />
          </SettingRow>
        </SettingsSection>

        <SettingsSection
          title="额外文件权限"
          description="工作区始终可访问；这里只添加工作区之外的目录。"
        >
          <SettingRow
            title="额外只读目录"
            description="允许读取，但不允许修改"
            wide
          >
            <StringListEditor
              values={draft.runtime.extraReadRoots}
              placeholder="/path/to/read-only"
              addLabel="添加只读目录"
              onChange={(extraReadRoots) => updateRuntime({ extraReadRoots })}
            />
          </SettingRow>
          <SettingRow
            title="额外可写目录"
            description="允许在这些目录中创建或修改文件"
            wide
          >
            <StringListEditor
              values={draft.runtime.extraWriteRoots}
              placeholder="/path/to/writable"
              addLabel="添加可写目录"
              onChange={(extraWriteRoots) => updateRuntime({ extraWriteRoots })}
            />
          </SettingRow>
        </SettingsSection>
      </>
    );
  }

  function renderSkillsPage() {
    return (
      <>
        {optionsError ? (
          <div className="settings-page-alert" role="alert">
            无法读取当前技能列表：{optionsError}
          </div>
        ) : null}
        <SkillsSettings
          skills={options.skills}
          errors={options.skill_errors}
          selectedNames={draft.context.skillNames}
          disabled={hasRunningSessions}
          onSelectedNamesChange={(skillNames) =>
            updateContext({ skillNames })
          }
          onOptionsChange={(nextOptions) => {
            setOptions(nextOptions);
            setOptionsError(null);
          }}
        />
      </>
    );
  }

  function renderMcpPage() {
    const normalizedSearch = mcpSearch.trim().toLowerCase();
    const visibleServers = draft.mcpServers
      .map((server, index) => ({ server, index }))
      .filter(({ server }) =>
        `${server.name} ${server.url}`.toLowerCase().includes(normalizedSearch),
      );

    return (
      <SettingsSection
        title="MCP 服务"
        description="连接外部工具来源；具体启用哪些工具请在“工具”分页中设置。"
      >
        <div className="mcp-service-list-heading">
          <span>
            {draft.mcpServers.length
              ? `${draft.mcpServers.length} 个已配置服务`
              : "尚未添加服务"}
          </span>
          <div className="mcp-service-list-actions">
            <button
              type="button"
              title={
                mcpConfigDirty
                  ? "请先保存 MCP 配置"
                  : "重新连接全部服务并获取最新工具"
              }
              disabled={
                !draft.mcpServers.length ||
                mcpConfigDirty ||
                mcpRefreshing !== null ||
                hasRunningSessions
              }
              onClick={() => void reloadMcp()}
            >
              <span
                className={mcpRefreshing === "*" ? "mcp-refresh-spinning" : ""}
                aria-hidden="true"
              >
                ↻
              </span>
              刷新全部
            </button>
            <button
              type="button"
              disabled={mcpRefreshing !== null}
              onClick={addMcpServer}
            >
              <span aria-hidden="true">＋</span>
              添加服务
            </button>
          </div>
        </div>

        {visibleServers.length ? (
          <div className="mcp-service-list">
            {visibleServers.map(({ server, index }) => {
              const status = options.mcp_statuses.find(
                (item) => item.name === server.name,
              );
              const persisted = sameMcpServer(
                server,
                settings.mcp_servers[index],
              );
              return (
                <div
                  className="mcp-service-row"
                  key={`${index}-${server.name}`}
                >
                  <button
                    type="button"
                    className="mcp-service-main"
                    onClick={() => openMcpEditor(index)}
                  >
                    <span
                      className={`mcp-service-icon${
                        status?.connected && persisted ? " connected" : ""
                      }`}
                      aria-hidden="true"
                    >
                      ⌁
                    </span>
                    <span className="mcp-service-copy">
                      <strong>{server.name || "未命名 MCP 服务"}</strong>
                      <span title={server.url}>
                        {server.url || "尚未填写 URL"}
                      </span>
                    </span>
                  </button>
                  <span className="mcp-service-meta">
                    <span>
                      {!persisted
                        ? "待保存"
                        : status?.connected
                        ? `已连接 · ${status.registered_tools.length} 个工具`
                        : "未连接"}
                    </span>
                  </span>
                  <button
                    type="button"
                    className="mcp-service-refresh"
                    aria-label={`刷新 ${server.name}`}
                    title={
                      persisted
                        ? "重新连接并获取最新工具"
                        : "请先保存 MCP 配置"
                    }
                    disabled={
                      !persisted ||
                      mcpRefreshing !== null ||
                      hasRunningSessions
                    }
                    onClick={() => void reloadMcp(server.name)}
                  >
                    <span
                      className={
                        mcpRefreshing === server.name
                          ? "mcp-refresh-spinning"
                          : ""
                      }
                      aria-hidden="true"
                    >
                      ↻
                    </span>
                  </button>
                  <button
                    type="button"
                    className="mcp-service-disclosure"
                    aria-label={`编辑 ${server.name}`}
                    onClick={() => openMcpEditor(index)}
                  >
                    ›
                  </button>
                </div>
              );
            })}
          </div>
        ) : (
          <div className="settings-empty-state">
            <div className="settings-empty-icon" aria-hidden="true">⌁</div>
            <strong>
              {mcpSearch.trim() ? "没有匹配的 MCP 服务" : "还没有配置 MCP 服务"}
            </strong>
            <span>
              {mcpSearch.trim()
                ? "尝试搜索其他名称或 URL。"
                : "添加并保存服务后，它提供的工具会出现在工具分页中。"}
            </span>
          </div>
        )}
      </SettingsSection>
    );
  }

  function renderMcpEditor() {
    if (!mcpEditor) return null;
    const headerEntries = Object.entries(mcpEditor.server.headers);
    const status =
      mcpEditor.index === null
        ? null
        : options.mcp_statuses.find(
            (item) =>
              item.name === draft.mcpServers[mcpEditor.index as number]?.name,
          );

    return (
      <div
        className="mcp-sheet-backdrop"
        role="presentation"
        onMouseDown={(event) => {
          if (event.target === event.currentTarget && !mcpTesting) {
            setMcpEditor(null);
            setMcpEditorError(null);
          }
        }}
      >
        <section
          className="mcp-sheet"
          role="dialog"
          aria-modal="true"
          aria-labelledby="mcp-sheet-title"
        >
          <header className="mcp-sheet-header">
            <div>
              <h2 id="mcp-sheet-title">
                {mcpEditor.index === null ? "添加 MCP 服务" : "MCP 服务设置"}
              </h2>
              <p>
                {mcpTesting
                  ? "正在测试连接并读取工具…"
                  : status?.connected
                  ? `已连接 · ${status.registered_tools.length} 个工具`
                  : "完成时会测试连接；保存设置后生效"}
              </p>
            </div>
            <button
              type="button"
              aria-label="关闭 MCP 设置"
              disabled={mcpTesting}
              onClick={() => {
                setMcpEditor(null);
                setMcpEditorError(null);
              }}
            >
              ×
            </button>
          </header>

          <div className="mcp-sheet-body">
            <div className="mcp-sheet-fields">
              <label>
                <span>名称</span>
                <input
                  value={mcpEditor.server.name}
                  disabled={mcpTesting}
                  placeholder="例如 github"
                  autoFocus
                  onChange={(event) =>
                    updateMcpEditor({ name: event.target.value })
                  }
                />
              </label>
              <label>
                <span>URL</span>
                <input
                  value={mcpEditor.server.url}
                  disabled={mcpTesting}
                  placeholder="https://example.com/mcp"
                  onChange={(event) =>
                    updateMcpEditor({ url: event.target.value })
                  }
                />
              </label>
            </div>

            <div className="mcp-sheet-headers">
              <div>
                <span>HTTP Headers</span>
                <small>已保存的值不会返回前端，留空表示保持不变</small>
              </div>
              {headerEntries.map(([name, value], headerIndex) => (
                <div
                  className="mcp-header-row"
                  key={`${headerIndex}-${name}`}
                >
                  <input
                    value={name}
                    disabled={mcpTesting}
                    placeholder="Authorization"
                    aria-label="Header 名称"
                    onChange={(event) => {
                      const nextEntries = [...headerEntries];
                      nextEntries[headerIndex] = [event.target.value, value];
                      updateMcpEditor({
                        headers: Object.fromEntries(nextEntries),
                      });
                    }}
                  />
                  <input
                    type="password"
                    value={value}
                    disabled={mcpTesting}
                    placeholder="已配置，留空表示不修改"
                    aria-label={`${name || "Header"} 值`}
                    onChange={(event) => {
                      const nextEntries = [...headerEntries];
                      nextEntries[headerIndex] = [name, event.target.value];
                      updateMcpEditor({
                        headers: Object.fromEntries(nextEntries),
                      });
                    }}
                  />
                  <button
                    className="settings-icon-button"
                    type="button"
                    disabled={mcpTesting}
                    aria-label="删除 Header"
                    onClick={() =>
                      updateMcpEditor({
                        headers: Object.fromEntries(
                          headerEntries.filter(
                            (_, index) => index !== headerIndex,
                          ),
                        ),
                      })
                    }
                  >
                    ×
                  </button>
                </div>
              ))}
              <button
                className="settings-add-button"
                type="button"
                disabled={
                  mcpTesting || Object.hasOwn(mcpEditor.server.headers, "")
                }
                onClick={() =>
                  updateMcpEditor({
                    headers: { ...mcpEditor.server.headers, "": "" },
                  })
                }
              >
                <span aria-hidden="true">＋</span>
                添加 Header
              </button>
            </div>

            {mcpEditorError ? (
              <div className="mcp-sheet-error" role="alert">
                {mcpEditorError}
              </div>
            ) : null}
          </div>

          <footer className="mcp-sheet-footer">
            <div>
              {mcpEditor.index !== null ? (
                <button
                  className="mcp-sheet-delete"
                  type="button"
                  disabled={mcpTesting}
                  onClick={deleteMcpServer}
                >
                  删除服务
                </button>
              ) : null}
            </div>
            <div>
              <button
                type="button"
                disabled={mcpTesting}
                onClick={() => {
                  setMcpEditor(null);
                  setMcpEditorError(null);
                }}
              >
                取消
              </button>
              <button
                className="primary"
                type="button"
                disabled={mcpTesting}
                onClick={() => void applyMcpEditor()}
              >
                {mcpTesting ? (
                  <>
                    <span className="mcp-button-spinner" aria-hidden="true" />
                    正在测试…
                  </>
                ) : (
                  "完成"
                )}
              </button>
            </div>
          </footer>
        </section>
      </div>
    );
  }

  function renderModelPicker() {
    if (!modelPickerOpen) return null;

    const emptyMessage = !draft.provider.baseUrl.trim()
      ? "请先填写 Base URL，或直接输入模型 ID"
      : !apiKey.trim() && !settings.provider.api_key_configured
          ? "请先填写 API Key，或直接输入模型 ID"
        : modelError
          ? "获取失败，可以重试或直接输入模型 ID"
          : "服务商没有返回模型，可直接输入模型 ID";

    return createPortal(
      <div
        ref={modelPopoverRef}
        className={`settings-model-popover${
          typeof modelPopoverStyle.left === "number" ? " positioned" : ""
        }`}
        style={modelPopoverStyle}
        role="dialog"
        aria-label="选择模型"
      >
        <label className="settings-model-search">
          <span aria-hidden="true" />
          <input
            ref={modelSearchRef}
            value={modelSearch}
            placeholder="搜索或输入模型 ID"
            aria-label="搜索或输入模型 ID"
            onChange={(event) => setModelSearch(event.target.value)}
          />
        </label>

        <div className="settings-model-results" role="listbox">
          {modelLoading ? (
            <div className="settings-model-loading">
              <span className="settings-model-spinner" aria-hidden="true" />
              正在从服务商获取模型…
            </div>
          ) : (
            <>
              {visibleModels.map((model) => {
                const selected = model === draft.provider.model;
                return (
                  <button
                    key={model}
                    ref={selected ? selectedModelRef : undefined}
                    type="button"
                    role="option"
                    aria-selected={selected}
                    title={model}
                    className={`settings-model-result${
                      selected ? " selected" : ""
                    }`}
                    onClick={() => chooseModel(model)}
                  >
                    <span className="settings-model-result-check">
                      {selected ? "✓" : ""}
                    </span>
                    <span>{model}</span>
                  </button>
                );
              })}

              {manualModelCandidate && !hasExactModel ? (
                <button
                  type="button"
                  role="option"
                  aria-selected="false"
                  className="settings-model-result manual"
                  onClick={() => chooseModel(manualModelCandidate)}
                >
                  <span className="settings-model-result-check">＋</span>
                  <span className="settings-model-manual-copy">
                    <strong>使用“{manualModelCandidate}”</strong>
                    <small>手动输入模型 ID</small>
                  </span>
                </button>
              ) : null}

              {!visibleModels.length && !manualModelCandidate ? (
                <div className="settings-model-empty">
                  <span className="settings-model-empty-icon" aria-hidden="true">
                    ◈
                  </span>
                  <strong>{emptyMessage}</strong>
                  {modelError ? (
                    <span>{modelError}</span>
                  ) : null}
                </div>
              ) : null}
            </>
          )}
        </div>

        <div className="settings-model-popover-footer">
          <span>
            {modelOptions.length
              ? modelSearch.trim()
                ? `${visibleModels.length} / ${modelOptions.length} 个模型`
                : `${modelOptions.length} 个模型`
              : "支持手动输入"}
          </span>
          <button
            type="button"
            disabled={modelLoading || !canFetchModels}
            onClick={() => void loadModels()}
          >
            <span aria-hidden="true">↻</span>
            {modelOptions.length ? "刷新" : "获取"}
          </button>
        </div>
      </div>,
      document.body,
    );
  }

  function renderPage() {
    switch (page) {
      case "provider":
        return renderProviderPage();
      case "context":
        return renderContextPage();
      case "tools":
        return renderToolsPage();
      case "skills":
        return renderSkillsPage();
      case "runtime":
        return renderRuntimePage();
    }
  }

  return (
    <>
      {!setupMode ? (
        <>
          <aside className="settings-sidebar">
            <div className="settings-sidebar-top">
            <button
              className="settings-back-button"
              type="button"
              onClick={requestClose}
            >
              <span aria-hidden="true">‹</span>
              返回对话
            </button>
            <div className="settings-sidebar-title">所有设置</div>
            <label className="settings-search">
              <span aria-hidden="true" />
              <input
                value={query}
                placeholder="搜索设置…"
                aria-label="搜索设置"
                onChange={(event) => setQuery(event.target.value)}
              />
            </label>
          </div>

          <nav className="settings-nav" aria-label="设置分类">
            {filteredNavItems.map((item) => (
              <button
                type="button"
                key={item.id}
                className={page === item.id ? "active" : ""}
                aria-current={page === item.id ? "page" : undefined}
                onClick={() => {
                  setPage(item.id);
                  if (item.id === "tools") setToolTab("tools");
                  setQuery("");
                }}
              >
                <span className="settings-nav-icon" aria-hidden="true">
                  {item.icon}
                </span>
                <span>{item.label}</span>
              </button>
            ))}
            {!filteredNavItems.length ? (
              <div className="settings-nav-empty">没有匹配的设置</div>
            ) : null}
          </nav>

          <div className="settings-sidebar-footer">
            <span>本地配置</span>
            <code>~/.bumblehive/config.json</code>
          </div>
        </aside>
        <div className="settings-divider" aria-hidden="true" />
      </>
      ) : null}

      <form
        ref={settingsContentRef}
        className={`settings-content${setupMode ? " settings-setup-content" : ""}`}
        onSubmit={submit}
      >
        <header className="settings-content-header">
          <div>
            <h1>{pageCopy.title}</h1>
            <p>{pageCopy.description}</p>
          </div>
          {canCancel ? (
            <button
              className="close-settings"
              type="button"
              aria-label="关闭设置"
              onClick={requestClose}
            >
              ×
            </button>
          ) : null}
        </header>

        {hasRunningSessions ? (
          <div className="settings-busy-banner">
            <span className="settings-busy-dot" aria-hidden="true" />
            有任务正在运行。你可以查看和编辑设置，任务完成后才能保存。
          </div>
        ) : null}

        <div className="settings-page">
          {setupMode ? renderProviderPage() : renderPage()}
        </div>
        {!setupMode ? renderMcpEditor() : null}

        <footer className="settings-savebar">
          <div className="settings-save-status">
            {error ? (
              <span className="settings-error-text" role="alert">{error}</span>
            ) : savedMessage ? (
              <span className="settings-success-text">{savedMessage}</span>
            ) : dirty ? (
              <span>有尚未保存的更改</span>
            ) : (
              <span>所有更改已保存</span>
            )}
          </div>
          <div className="settings-save-actions">
            {!setupMode ? (
              <button
                type="button"
                className="secondary-button"
                disabled={!dirty || saving}
                onClick={resetDraft}
              >
                放弃更改
              </button>
            ) : null}
            <button
              type="submit"
              className="primary-button"
              disabled={!dirty || saving || hasRunningSessions}
            >
              {saving ? "保存中…" : setupMode ? "保存并开始" : "保存设置"}
            </button>
          </div>
        </footer>
      </form>
      {renderModelPicker()}
    </>
  );
}
