import {
  memo,
  useState,
  useRef,
  useLayoutEffect,
  type ReactNode,
  type FormEvent,
  type KeyboardEvent,
} from "react";
import type { ApprovalMode, PendingChatMessage } from "../types/api";
import { ApprovalModeSelect } from "./ApprovalModeSelect";
import { ModelOptions } from "./ModelOptions";

interface ComposerProps {
  approvalSlot?: ReactNode;
  questionSlot?: ReactNode;
  pendingMessages?: PendingChatMessage[];
  disconnected?: boolean;
  onPendingAction?: (messageId: string, type: "steer" | "remove_pending") => void;
  approvalMode: ApprovalMode;
  onSelectApprovalMode: (mode: ApprovalMode) => void;
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
  approvalSlot,
  questionSlot,
  pendingMessages = [],
  disconnected = false,
  onPendingAction,
  approvalMode,
  onSelectApprovalMode,
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
  const composerRef = useRef<HTMLFormElement>(null);
  const accessoryRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const hasApproval = Boolean(approvalSlot);
  const wasApproving = useRef(false);
  useLayoutEffect(() => {
    const composer = composerRef.current;
    const panel = composer?.closest<HTMLElement>(".main-panel");
    if (!composer || !panel) return;
    const measure = () => panel.style.setProperty(
      "--composer-space",
      `${composer.offsetHeight + (accessoryRef.current?.offsetHeight ?? 0)}px`,
    );
    const observer = new ResizeObserver(measure);
    observer.observe(composer);
    if (accessoryRef.current) observer.observe(accessoryRef.current);
    measure();
    return () => {
      observer.disconnect();
      panel.style.removeProperty("--composer-space");
    };
  }, []);
  const [modelMenuOpen, setModelMenuOpen] = useState(false);
  useLayoutEffect(() => {
    if (hasApproval) setModelMenuOpen(false);
    else if (wasApproving.current) inputRef.current?.focus({ preventScroll: true });
    wasApproving.current = hasApproval;
  }, [hasApproval]);
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (hasApproval || disabled || disconnected || isStopping) return;
    onSubmit();
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      event.currentTarget.form?.requestSubmit();
    }
  }

  return (
    <form className={`composer${hasApproval ? " composer-approving" : ""}`} onSubmit={submit} ref={composerRef}>
      <div className="composer-accessory" ref={accessoryRef}>
        {questionSlot}
        {pendingMessages.length > 0 ? (
          <div
            className="pending-messages"
            aria-label="待发送消息"
            onClickCapture={(event) => {
              if (event.detail > 1) event.stopPropagation();
            }}
          >
            {pendingMessages.map((message) => (
              <div className="pending-message" key={message.message_id}>
                <svg className="pending-queue-icon" viewBox="0 0 20 20" aria-hidden="true">
                  <path d="M4 3v11h12m-3-3 3 3-3 3M8 5h7M8 9h5" />
                </svg>
                <span className="pending-message-content" title={message.content}>
                  {message.content}
                </span>
                <button
                  type="button"
                  className="pending-steer"
                  disabled={message.submitting || disconnected || isStopping}
                  onClick={() => onPendingAction?.(message.message_id, "steer")}
                >
                  <span aria-hidden="true">↳</span> {isStreaming ? "引导" : "发送"}
                </button>
                <button
                  type="button"
                  className="pending-remove"
                  aria-label={`删除待发送消息：${message.content}`}
                  disabled={message.submitting || disconnected}
                  onClick={() => onPendingAction?.(message.message_id, "remove_pending")}
                >
                  <svg viewBox="0 0 20 20" aria-hidden="true">
                    <path d="M3 5h14M7 5V3h6v2M5 5l1 12h8l1-12M8 8v6M12 8v6" />
                  </svg>
                </button>
              </div>
            ))}
          </div>
        ) : null}
      </div>
      {hasApproval ? approvalSlot : (
        <>
          {disconnected ? (
            <div className="composer-connection" role="status">连接已中断，正在重新连接…</div>
          ) : null}
          <textarea
            ref={inputRef}
            value={value}
            disabled={disabled}
            aria-label="输入任务"
            placeholder={
              isStreaming ? "继续输入，提交后排队，也可选择引导…" : "给 BumbleHive 一个任务…"
            }
            onChange={(event) => onChange(event.target.value)}
            onKeyDown={handleKeyDown}
          />
          <div className="composer-toolbar">
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
            <ApprovalModeSelect
              mode={approvalMode}
              disabled={disabled || isStreaming}
              onSelect={onSelectApprovalMode}
            />
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
            {isStreaming && value.trim() ? (
              <button className="queue-submit" type="submit" disabled={disabled || disconnected || isStopping}>
                排队发送
              </button>
            ) : null}
            <button
              className="send-button"
              type={isStreaming ? "button" : "submit"}
              disabled={
                disabled || disconnected || isStopping || (!isStreaming && !value.trim())
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
        </>
      )}
    </form>
  );
});
