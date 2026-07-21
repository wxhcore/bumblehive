import { useEffect, useState, type FormEvent } from "react";
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
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setApiKey("");
    setModel(settings.provider.model ?? "");
    setBaseUrl(settings.provider.base_url || "");
    setWorkspace(settings.runtime?.workspace || "");
  }, [settings]);

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
            <input
              value={model}
              required
              placeholder="请输入模型名称"
              onChange={(event) => setModel(event.target.value)}
            />
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
