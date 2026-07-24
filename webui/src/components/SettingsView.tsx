import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
} from "react";
import { getModels } from "../api/http";
import { ModelOptions } from "./ModelOptions";
import type { Settings, SettingsUpdate } from "../types/api";

interface SettingsViewProps {
  settings: Settings;
  canCancel: boolean;
  onCancel: () => void;
  onSave: (update: SettingsUpdate) => Promise<void>;
}

export function SettingsView({
  settings,
  canCancel,
  onCancel,
  onSave,
}: SettingsViewProps) {
  const [apiKey, setApiKey] = useState("");
  const [model, setModel] = useState(settings.provider.model ?? "");
  const [baseUrl, setBaseUrl] = useState(settings.provider.base_url || "");
  const [workspace, setWorkspace] = useState(settings.runtime?.workspace || "");
  const [modelOptions, setModelOptions] = useState<string[]>([]);
  const [modelMenuOpen, setModelMenuOpen] = useState(false);
  const [modelStatus, setModelStatus] = useState<string | null>(null);
  const [modelLoading, setModelLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const modelRequestId = useRef(0);

  useEffect(() => {
    modelRequestId.current += 1;
    setApiKey("");
    setModel(settings.provider.model ?? "");
    setBaseUrl(settings.provider.base_url || "");
    setWorkspace(settings.runtime?.workspace || "");
    setModelOptions([]);
    setModelMenuOpen(false);
    setModelStatus(null);
    setModelLoading(false);
  }, [settings]);

  const loadModels = useCallback(async (options?: { openMenu?: boolean }) => {
    const requestId = ++modelRequestId.current;
    setModelLoading(true);
    setModelStatus(null);
    try {
      const apiKeyValue = apiKey.trim();
      const response = await getModels({
        base_url: baseUrl.trim(),
        ...(apiKeyValue ? { api_key: apiKeyValue } : {}),
      });
      const nextModels = Array.from(
        new Set(
          response.models
            .map((item) => item.trim())
            .filter((item) => Boolean(item)),
        ),
      );
      if (requestId !== modelRequestId.current) {
        return;
      }
      setModelOptions(nextModels);
      if (options?.openMenu && nextModels.length > 0) {
        setModelMenuOpen(true);
      }
      setModelStatus(
        nextModels.length > 0
          ? `已读取 ${nextModels.length} 个模型`
          : "未读取到模型列表，可直接手动输入",
      );
    } catch (reason) {
      if (requestId !== modelRequestId.current) {
        return;
      }
      setModelOptions([]);
      setModelMenuOpen(false);
      setModelStatus(
        reason instanceof Error ? reason.message : "模型列表加载失败",
      );
    } finally {
      if (requestId !== modelRequestId.current) {
        return;
      }
      setModelLoading(false);
    }
  }, [apiKey, baseUrl]);

  const visibleModels = useMemo(() => {
    const query = model.trim().toLowerCase();
    if (!query) {
      return modelOptions;
    }

    return modelOptions.filter((item) => item.toLowerCase().includes(query));
  }, [model, modelOptions]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);

    const resolvedModel = model.trim();
    if (!resolvedModel) {
      setError("请输入模型名称");
      return;
    }

    const provider: Record<string, unknown> = {
      model: resolvedModel,
      base_url: baseUrl.trim() || null,
    };
    if (apiKey.trim()) provider.api_key = apiKey.trim();

    setSaving(true);
    try {
      await onSave({
        provider,
        runtime: {
          workspace: workspace.trim() || null,
        },
      });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "设置保存失败");
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="settings-view">
      <div className="settings-card">
        <div className="settings-heading">
          <div>
            <span className="settings-kicker">BumbleHive</span>
            <h1>{canCancel ? "设置" : "开始前完成设置"}</h1>
          </div>
          {canCancel ? (
            <button className="close-settings" type="button" onClick={onCancel}>
              ×
            </button>
          ) : null}
        </div>

        <form className="settings-form" onSubmit={submit}>
          <label>
            <span>Base URL</span>
            <input
              type="url"
              value={baseUrl}
              placeholder="https://api.openai.com/v1"
              onChange={(event) => setBaseUrl(event.target.value)}
            />
          </label>

          <label>
            <span>API Key</span>
            <input
              type="password"
              value={apiKey}
              required={!settings.provider.api_key_configured}
              autoComplete="off"
              placeholder={
                settings.provider.api_key_configured
                  ? "已配置，留空表示不修改"
                  : "请输入 API Key"
              }
              onChange={(event) => setApiKey(event.target.value)}
            />
          </label>

          <label>
            <span>Model Name</span>
            <div
              className="model-field"
              onBlur={(event) => {
                const nextTarget = event.relatedTarget;
                if (
                  !(nextTarget instanceof Node) ||
                  !event.currentTarget.contains(nextTarget)
                ) {
                  setModelMenuOpen(false);
                }
              }}
            >
              <div className="model-input-row">
                <input
                  value={model}
                  required
                  placeholder="输入当前会话可用的模型"
                  onFocus={() => setModelMenuOpen(true)}
                  onChange={(event) => {
                    setModel(event.target.value);
                    setModelMenuOpen(true);
                  }}
                  onKeyDown={(event) => {
                    if (event.key === "Escape") {
                      setModelMenuOpen(false);
                    }
                    if (event.key === "ArrowDown") {
                      setModelMenuOpen(true);
                    }
                  }}
                />
                <button
                  type="button"
                  className="secondary-button model-refresh-button"
                  onClick={() => {
                    void loadModels({ openMenu: true });
                  }}
                  disabled={modelLoading || saving}
                >
                  {modelLoading ? "读取中…" : "刷新模型"}
                </button>
                <button
                  type="button"
                  className="model-clear-button"
                  onClick={() => {
                    setModel("");
                    setModelMenuOpen(true);
                  }}
                  disabled={saving || !model.trim()}
                  aria-label="清空模型"
                >
                  ×
                </button>
              </div>
              {modelMenuOpen && modelOptions.length > 0 ? (
                <div className="model-dropdown" role="listbox">
                  <ModelOptions
                    models={visibleModels}
                    selectedModel={model}
                    emptyMessage="没有匹配的模型"
                    onSelect={(item) => {
                      setModel(item);
                      setModelMenuOpen(false);
                    }}
                  />
                </div>
              ) : null}
              {modelStatus ? (
                <div className="model-status">{modelStatus}</div>
              ) : null}
            </div>
          </label>

          <label>
            <span>工作区</span>
            <input
              value={workspace}
              placeholder="留空使用默认工作区"
              onChange={(event) => setWorkspace(event.target.value)}
            />
          </label>

          {error ? <div className="settings-error">{error}</div> : null}

          <div className="settings-actions">
            {canCancel ? (
              <button type="button" className="secondary-button" onClick={onCancel}>
                取消
              </button>
            ) : null}
            <button type="submit" className="primary-button" disabled={saving}>
              {saving ? "保存中…" : "保存设置"}
            </button>
          </div>
        </form>
      </div>
    </section>
  );
}
