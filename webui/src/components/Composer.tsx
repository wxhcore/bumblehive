import type { FormEvent, KeyboardEvent } from "react";

interface ComposerProps {
  value: string;
  model: string;
  workspace: string;
  disabled: boolean;
  isStreaming: boolean;
  isStopping: boolean;
  onChange: (value: string) => void;
  onSubmit: () => void;
  onStop: () => void;
  onOpenSettings: () => void;
}

export function Composer({
  value,
  model,
  workspace,
  disabled,
  isStreaming,
  isStopping,
  onChange,
  onSubmit,
  onStop,
  onOpenSettings,
}: ComposerProps) {
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (isStreaming) return;
    onSubmit();
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      event.currentTarget.form?.requestSubmit();
    }
  }

  return (
    <form className="composer" onSubmit={submit}>
      <textarea
        value={value}
        disabled={disabled}
        aria-label="输入任务"
        placeholder={
          isStreaming ? "BumbleHive 正在回答…" : "给 BumbleHive 一个任务…"
        }
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={handleKeyDown}
      />
      <div className="composer-toolbar">
        <button
          className="tool-button"
          type="button"
          aria-label="附件功能暂未开放"
          title="附件功能暂未开放"
          disabled
        >
          <span className="plus-icon tool-plus" aria-hidden="true" />
        </button>
        <button
          className="workspace-button"
          type="button"
          aria-label={`当前工作区 ${workspace}`}
          disabled={disabled || isStreaming}
          onClick={onOpenSettings}
        >
          <span className="folder-icon" aria-hidden="true" />
          <span>{workspace}</span>
        </button>
        <span className="toolbar-spacer" />
        <button
          className="model-button"
          type="button"
          aria-label={`当前模型 ${model}`}
          disabled={disabled || isStreaming}
          onClick={onOpenSettings}
        >
          <span>{model}</span>
          <span className="chevron" aria-hidden="true" />
        </button>
        <button
          className="send-button"
          type={isStreaming ? "button" : "submit"}
          disabled={
            disabled || isStopping || (!isStreaming && !value.trim())
          }
          aria-label={isStreaming ? "停止运行" : "发送任务"}
          onClick={isStreaming ? onStop : undefined}
        >
          <span
            className={isStreaming ? "stop-icon" : "send-arrow"}
            aria-hidden="true"
          />
        </button>
      </div>
    </form>
  );
}
