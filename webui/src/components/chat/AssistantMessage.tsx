import { memo, useEffect, useMemo, useRef, useState } from "react";
import type { AssistantIteration, UiMessage } from "../../types/api";
import { ReasoningBlock, StreamedMarkdown } from "./MarkdownContent";
import { consolidateShellIterations, ToolSteps } from "./ToolActivityList";

interface AssistantIterationViewProps {
  modelIteration: AssistantIteration;
  reasoningActive?: boolean;
  expandReasoning?: boolean;
  showReasoning?: boolean;
  streaming?: boolean;
}

export function iterationsOutsideExecutionProcess(
  iterations: AssistantIteration[],
  executionIterations: AssistantIteration[],
  finalAnswerIteration: AssistantIteration | null,
  active: boolean,
): AssistantIteration[] {
  if (active) return [];
  if (finalAnswerIteration) return [finalAnswerIteration];
  return executionIterations.length ? [] : iterations;
}

const AssistantIterationView = memo(function AssistantIterationView({
  modelIteration,
  reasoningActive = false,
  expandReasoning = false,
  showReasoning = true,
  streaming = false,
}: AssistantIterationViewProps) {
  return (
    <div className="assistant-iteration">
      {showReasoning && modelIteration.reasoning ? (
        <ReasoningBlock
          content={modelIteration.reasoning}
          active={reasoningActive}
          defaultOpen={expandReasoning}
          streaming={streaming}
        />
      ) : null}
      {modelIteration.content ? (
        <div className="message-content markdown-body">
          <StreamedMarkdown content={modelIteration.content} />
        </div>
      ) : null}
      {modelIteration.tools?.length ? (
        <ToolSteps tools={modelIteration.tools} />
      ) : null}
    </div>
  );
});

function formatElapsedTime(seconds: number): string {
  const totalSeconds = Math.max(0, Math.round(seconds));
  if (totalSeconds < 60) return `${totalSeconds}s`;
  const minutes = Math.floor(totalSeconds / 60);
  const remainingSeconds = totalSeconds % 60;
  if (minutes < 60) {
    return remainingSeconds
      ? `${minutes}m ${remainingSeconds}s`
      : `${minutes}m`;
  }
  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  return [
    `${hours}h`,
    remainingMinutes ? `${remainingMinutes}m` : "",
    remainingSeconds ? `${remainingSeconds}s` : "",
  ]
    .filter(Boolean)
    .join(" ");
}

const ExecutionProcessLabel = memo(function ExecutionProcessLabel({
  active,
  durationSeconds,
  error,
  startedAt,
  stopped,
}: {
  active: boolean;
  durationSeconds?: number;
  error: boolean;
  startedAt?: number;
  stopped: boolean;
}) {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (!active || startedAt === undefined) return undefined;
    setNow(Date.now());
    const timer = window.setInterval(() => setNow(Date.now()), 1_000);
    return () => window.clearInterval(timer);
  }, [active, startedAt]);

  const elapsed =
    durationSeconds ??
    (startedAt === undefined ? undefined : Math.max(0, (now - startedAt) / 1000));
  const status = active
    ? "干活中"
    : error
      ? "处理失败"
      : stopped
        ? "已停止"
        : "已结束";
  return (
    <>
      <span>{status}</span>
      {elapsed !== undefined ? (
        <span className="execution-process-time">
          {formatElapsedTime(elapsed)}
        </span>
      ) : null}
    </>
  );
});

const ExecutionProcess = memo(function ExecutionProcess({
  iterations,
  active,
  durationSeconds,
  error,
  startedAt,
  stopped,
}: {
  iterations: AssistantIteration[];
  active: boolean;
  durationSeconds?: number;
  error: boolean;
  startedAt?: number;
  stopped: boolean;
}) {
  const [open, setOpen] = useState(active);
  const wasActive = useRef(active);

  useEffect(() => {
    if (active) setOpen(true);
    if (!active && wasActive.current) setOpen(false);
    wasActive.current = active;
  }, [active]);

  return (
    <section className={`execution-process${open ? " open" : ""}`}>
      <div className="execution-process-header">
        <button
          className="execution-process-toggle"
          type="button"
          aria-expanded={open}
          onClick={() => setOpen((current) => !current)}
        >
          <ExecutionProcessLabel
            active={active}
            durationSeconds={durationSeconds}
            error={error}
            startedAt={startedAt}
            stopped={stopped}
          />
          <span className="execution-process-chevron" aria-hidden="true" />
        </button>
      </div>
      {open && iterations.length ? (
        <div className="execution-process-content">
          {iterations.map((iteration) => (
            <AssistantIterationView
              modelIteration={iteration}
              expandReasoning
              key={iteration.id}
            />
          ))}
        </div>
      ) : null}
    </section>
  );
});

export const MessageView = memo(function MessageView({
  message,
  active,
}: {
  message: UiMessage;
  active: boolean;
}) {
  const iterations = useMemo(
    () => consolidateShellIterations(message.iterations ?? []),
    [message.iterations],
  );
  const waiting =
    active &&
    !iterations.some(
      (item) =>
        item.content || item.reasoning || Boolean(item.tools?.length),
    );
  const lastIteration = iterations.at(-1);
  const finalAnswerIteration =
    !active &&
    !message.error &&
    !message.stopped &&
    lastIteration?.content.trim() &&
    !lastIteration.tools?.length
      ? lastIteration
      : null;
  const hasToolCalls = iterations.some((iteration) =>
    Boolean(iteration.tools?.length),
  );
  const hasReasoning = iterations.some((iteration) =>
    Boolean(iteration.reasoning),
  );
  const executionIterations =
    finalAnswerIteration && (hasToolCalls || hasReasoning)
      ? [
          ...iterations.slice(0, -1),
          ...(finalAnswerIteration.reasoning
            ? [
                {
                  ...finalAnswerIteration,
                  id: `${finalAnswerIteration.id}-reasoning`,
                  content: "",
                  tools: undefined,
                },
              ]
            : []),
        ].filter(
          (item) =>
            item.content || item.reasoning || Boolean(item.tools?.length),
        )
      : !active && (message.error || message.stopped)
        ? iterations
      : [];
  const processIterations = active ? iterations : executionIterations;
  const visibleIterations = iterationsOutsideExecutionProcess(
    iterations,
    executionIterations,
    finalAnswerIteration,
    active,
  );

  return (
    <article
      className={`message message-${message.role}${
        message.error ? " message-error" : ""
      }`}
    >
      {message.role === "assistant" ? (
        <>
          {active || executionIterations.length ? (
            <ExecutionProcess
              active={active}
              durationSeconds={message.durationSeconds}
              error={Boolean(message.error)}
              iterations={processIterations}
              startedAt={message.startedAt}
              stopped={Boolean(message.stopped)}
            />
          ) : null}
          {visibleIterations.map((modelIteration, iterationIndex) => {
            const iterationActive =
              active &&
              iterationIndex === visibleIterations.length - 1;
            const reasoningActive =
              iterationActive &&
              Boolean(modelIteration.reasoning) &&
              !modelIteration.content &&
              !modelIteration.tools?.length;
            return (
              <AssistantIterationView
                modelIteration={modelIteration}
                reasoningActive={reasoningActive}
                showReasoning={
                  !(finalAnswerIteration && (hasToolCalls || hasReasoning))
                }
                streaming={iterationActive}
                key={modelIteration.id}
              />
            );
          })}
          {waiting ? (
            <div className="message-content">
              <span className="typing-dots" aria-label="正在生成">
                <i />
                <i />
                <i />
              </span>
            </div>
          ) : null}
          {message.stopped ? (
            <div className="run-stopped">已停止</div>
          ) : null}
        </>
      ) : (
        <>
          {message.role === "tool" ? (
            <div className="message-role">工具</div>
          ) : null}
          {message.content ? (
            <div className="message-content">{message.content}</div>
          ) : null}
        </>
      )}
    </article>
  );
});
