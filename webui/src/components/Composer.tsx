import {
  memo,
  useState,
  type FormEvent,
  type KeyboardEvent,
} from "react";
import { ModelOptions } from "./ModelOptions";

interface ComposerProps {
  value: string;
  model: string;
  models: string[];
  workspace: string;
  disabled: boolean;
  isStreaming: boolean;
  isStopping: boolean;
  modelSwitchDisabled: boolean;
  onChange: (value: string) => void;
  onSubmit: () => void;
  onStop: () => void;
  onAddWorkspace: () => void;
  onSelectModel: (model: string) => Promise<void>;
}

export const Composer = memo(function Composer({
  value,
  model,
  models,
  workspace,
  disabled,
  isStreaming,
  isStopping,
  modelSwitchDisabled,
  onChange,
  onSubmit,
  onStop,
  onAddWorkspace,
  onSelectModel,
}: ComposerProps) {
  const [modelMenuOpen, setModelMenuOpen] = useState(false);
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
          aria-label={`新建工作空间，当前工作区 ${workspace}`}
          title="新建工作空间"
          disabled={disabled || isStreaming}
          onClick={onAddWorkspace}
        >
          <span className="folder-icon" aria-hidden="true" />
          <span>{workspace}</span>
        </button>
        <span className="toolbar-spacer" />
        <div
          className="composer-model-field"
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
          {modelMenuOpen && !modelSwitchDisabled ? (
            <div className="model-dropdown composer-model-dropdown" role="listbox">
              <ModelOptions
                models={models}
                selectedModel={model}
                onSelect={(selectedModel) => {
                  setModelMenuOpen(false);
                  void onSelectModel(selectedModel);
                }}
              />
            </div>
          ) : null}
          <button
            className="model-button"
            type="button"
            aria-label={`当前模型 ${model}`}
            aria-expanded={modelMenuOpen}
            disabled={disabled || modelSwitchDisabled}
            onClick={() => setModelMenuOpen((open) => !open)}
          >
            <span>{model}</span>
            <span className="chevron" aria-hidden="true" />
          </button>
        </div>
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
});
