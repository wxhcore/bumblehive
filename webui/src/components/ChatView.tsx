import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type {
  AssistantIteration,
  ToolActivity,
  UiMessage,
} from "../types/api";
import { getToolPresentation } from "./tool-presentation";

interface ChatViewProps {
  messages: UiMessage[];
  isStreaming: boolean;
}

interface ReasoningBlockProps {
  content: string;
  active: boolean;
  defaultOpen?: boolean;
}

function ReasoningBlock({
  content,
  active,
  defaultOpen = false,
}: ReasoningBlockProps) {
  const [open, setOpen] = useState(active || defaultOpen);
  const wasActive = useRef(active);

  useEffect(() => {
    if (active) setOpen(true);
    if (!active && wasActive.current) setOpen(false);
    wasActive.current = active;
  }, [active]);

  return (
    <section className={`reasoning-block${active ? " active" : ""}`}>
      <button
        className="reasoning-toggle"
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((current) => !current)}
      >
        <span className="reasoning-status" aria-hidden="true" />
        <span>{active ? "正在思考" : "思考过程"}</span>
        <span
          className={`reasoning-chevron${open ? " open" : ""}`}
          aria-hidden="true"
        />
      </button>
      {open ? (
        <div className="reasoning-content markdown-body">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
        </div>
      ) : null}
    </section>
  );
}

function ToolSteps({ tools }: { tools: ToolActivity[] }) {
  return (
    <div className="tool-steps" aria-label="工具调用">
      {tools.map((tool) => {
        const running = tool.status === "running" || tool.status === "preparing";
        const presentation = getToolPresentation(tool);
        return (
          <div
            className={`tool-step tool-step-${tool.status}`}
            key={tool.id}
            title={[
              `工具：${presentation.technicalName}`,
              tool.errorMessage,
            ]
              .filter(Boolean)
              .join("\n")}
          >
            <span
              className={`tool-step-icon${running ? " running" : ""}`}
              aria-hidden="true"
            >
              {running
                ? ""
                : tool.status === "completed"
                  ? "✓"
                  : tool.status === "cancelled"
                    ? "■"
                    : "!"}
            </span>
            <span className="tool-step-name">{presentation.label}</span>
            <span className="tool-step-summary">{presentation.summary}</span>
            <span className="tool-step-status">{presentation.duration}</span>
          </div>
        );
      })}
    </div>
  );
}

interface AssistantIterationViewProps {
  modelIteration: AssistantIteration;
  reasoningActive?: boolean;
  expandReasoning?: boolean;
}

function AssistantIterationView({
  modelIteration,
  reasoningActive = false,
  expandReasoning = false,
}: AssistantIterationViewProps) {
  return (
    <div className="assistant-iteration">
      {modelIteration.reasoning ? (
        <ReasoningBlock
          content={modelIteration.reasoning}
          active={reasoningActive}
          defaultOpen={expandReasoning}
        />
      ) : null}
      {modelIteration.content ? (
        <div className="message-content markdown-body">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>
            {modelIteration.content}
          </ReactMarkdown>
        </div>
      ) : null}
      {modelIteration.tools?.length ? (
        <ToolSteps tools={modelIteration.tools} />
      ) : null}
    </div>
  );
}

function ExecutionProcess({
  iterations,
}: {
  iterations: AssistantIteration[];
}) {
  const [open, setOpen] = useState(false);
  const hasTools = iterations.some(
    (iteration) => Boolean(iteration.tools?.length),
  );

  return (
    <section className={`execution-process${open ? " open" : ""}`}>
      <button
        className="execution-process-toggle"
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((current) => !current)}
      >
        <span className="execution-process-check" aria-hidden="true">
          ✓
        </span>
        <span>{hasTools ? "已完成执行过程" : "思考过程"}</span>
        <span className="execution-process-chevron" aria-hidden="true" />
      </button>
      {open ? (
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
}

export function ChatView({ messages, isStreaming }: ChatViewProps) {
  const scrollRef = useRef<HTMLElement>(null);
  const stickToBottomRef = useRef(true);

  useEffect(() => {
    const scrollContainer = scrollRef.current;
    if (!scrollContainer || !stickToBottomRef.current) return;
    const frame = window.requestAnimationFrame(() => {
      scrollContainer.scrollTop = scrollContainer.scrollHeight;
    });
    return () => window.cancelAnimationFrame(frame);
  }, [messages]);

  function updateStickToBottom() {
    const scrollContainer = scrollRef.current;
    if (!scrollContainer) return;
    const distanceFromBottom =
      scrollContainer.scrollHeight -
      scrollContainer.scrollTop -
      scrollContainer.clientHeight;
    stickToBottomRef.current = distanceFromBottom <= 72;
  }

  return (
    <section
      className="chat-view"
      aria-live="polite"
      ref={scrollRef}
      onScroll={updateStickToBottom}
      onWheel={(event) => {
        if (event.deltaY < 0) stickToBottomRef.current = false;
      }}
    >
      <div className="message-list">
        {messages.map((message, index) => {
          const active =
            isStreaming &&
            message.role === "assistant" &&
            index === messages.length - 1;
          const iterations = message.iterations ?? [];
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
          const executionIterations = finalAnswerIteration && hasToolCalls
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
            : [];

          return (
            <article
              className={`message message-${message.role}${
                message.error ? " message-error" : ""
              }`}
              key={message.id}
            >
              {message.role === "assistant" ? (
                <>
                  {finalAnswerIteration ? (
                    <>
                      {executionIterations.length ? (
                        <ExecutionProcess iterations={executionIterations} />
                      ) : finalAnswerIteration.reasoning ? (
                        <ReasoningBlock
                          content={finalAnswerIteration.reasoning}
                          active={false}
                        />
                      ) : null}
                      <div className="message-content markdown-body">
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>
                          {finalAnswerIteration.content}
                        </ReactMarkdown>
                      </div>
                    </>
                  ) : (
                    iterations.map((modelIteration, iterationIndex) => {
                      const reasoningActive =
                        active &&
                        iterationIndex === iterations.length - 1 &&
                        Boolean(modelIteration.reasoning) &&
                        !modelIteration.content &&
                        !modelIteration.tools?.length;
                      return (
                        <AssistantIterationView
                          modelIteration={modelIteration}
                          reasoningActive={reasoningActive}
                          key={modelIteration.id}
                        />
                      );
                    })
                  )}
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
        })}
        <div className="message-scroll-anchor" />
      </div>
    </section>
  );
}
