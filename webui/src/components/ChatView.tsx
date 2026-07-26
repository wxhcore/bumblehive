import { memo, useEffect, useMemo, useRef, useState } from "react";
import type {
  KeyboardEvent as ReactKeyboardEvent,
  PointerEvent as ReactPointerEvent,
} from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type {
  AssistantIteration,
  ToolActivity,
  UiMessage,
} from "../types/api";
import { getToolPresentation } from "./tool-presentation";

const MARKDOWN_PLUGINS = [remarkGfm];
const AUTO_SCROLL_TIME_CONSTANT_MS = 42;
const MIN_SCROLLBAR_THUMB_SIZE = 32;

interface ChatViewProps {
  messages: UiMessage[];
  isStreaming: boolean;
}

interface ReasoningBlockProps {
  content: string;
  active: boolean;
  defaultOpen?: boolean;
  streaming?: boolean;
}

const StreamedMarkdown = memo(function StreamedMarkdown({
  content,
}: {
  content: string;
}) {
  return (
    <ReactMarkdown remarkPlugins={MARKDOWN_PLUGINS}>
      {content}
    </ReactMarkdown>
  );
});

const ReasoningBlock = memo(function ReasoningBlock({
  content,
  active,
  defaultOpen = false,
  streaming = false,
}: ReasoningBlockProps) {
  const [open, setOpen] = useState(streaming || active || defaultOpen);
  const wasStreaming = useRef(streaming);

  useEffect(() => {
    if (streaming) setOpen(true);
    if (!streaming && wasStreaming.current) setOpen(false);
    wasStreaming.current = streaming;
  }, [streaming]);

  return (
    <section className={`reasoning-block${active ? " active" : ""}`}>
      <button
        className="reasoning-toggle"
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((current) => !current)}
      >
        <span>{active ? "正在思考" : "思考过程"}</span>
        <span
          className={`reasoning-chevron${open ? " open" : ""}`}
          aria-hidden="true"
        />
      </button>
      {open ? (
        <div className="reasoning-content markdown-body">
          <StreamedMarkdown content={content} />
        </div>
      ) : null}
    </section>
  );
});

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
  showReasoning?: boolean;
  streaming?: boolean;
}

const AssistantIterationView = memo(function AssistantIterationView({
  modelIteration,
  reasoningActive = false,
  expandReasoning = false,
  streaming = false,
}: AssistantIterationViewProps) {
  return (
    <div className="assistant-iteration">
      {modelIteration.reasoning ? (
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
        : "已完成";
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

const MessageView = memo(function MessageView({
  message,
  active,
}: {
  message: UiMessage;
  active: boolean;
}) {
  const iterations = useMemo(
    () => message.iterations ?? [],
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
  const visibleIterations = active
    ? []
    : finalAnswerIteration
    ? [finalAnswerIteration]
    : iterations;

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

export function ChatView({ messages, isStreaming }: ChatViewProps) {
  const scrollRef = useRef<HTMLElement>(null);
  const messageListRef = useRef<HTMLDivElement>(null);
  const scrollbarTrackRef = useRef<HTMLDivElement>(null);
  const scrollbarThumbRef = useRef<HTMLDivElement>(null);
  const stickToBottomRef = useRef(true);
  const userPausedAutoScrollRef = useRef(false);
  const autoScrollFrameRef = useRef<number | null>(null);
  const autoScrollTimestampRef = useRef<number | null>(null);
  const scrollbarUpdateFrameRef = useRef<number | null>(null);
  const animateAutoScrollRef = useRef<(timestamp: number) => void>(
    () => undefined,
  );
  const updateScrollbarRef = useRef<() => void>(() => undefined);
  const scrollbarMetricsRef = useRef({
    maxScroll: 0,
    thumbHeight: MIN_SCROLLBAR_THUMB_SIZE,
    thumbTravel: 0,
  });
  const thumbDragRef = useRef<{
    pointerId: number;
    startY: number;
    startScrollTop: number;
  } | null>(null);

  function scheduleScrollbarUpdate() {
    if (scrollbarUpdateFrameRef.current !== null) return;
    scrollbarUpdateFrameRef.current = window.requestAnimationFrame(() => {
      scrollbarUpdateFrameRef.current = null;
      updateScrollbarRef.current();
    });
  }

  function stopAutoScroll() {
    if (autoScrollFrameRef.current !== null) {
      window.cancelAnimationFrame(autoScrollFrameRef.current);
      autoScrollFrameRef.current = null;
    }
    autoScrollTimestampRef.current = null;
  }

  function pauseAutoScroll() {
    userPausedAutoScrollRef.current = true;
    stickToBottomRef.current = false;
    stopAutoScroll();
  }

  function startAutoScroll() {
    if (
      autoScrollFrameRef.current !== null ||
      userPausedAutoScrollRef.current ||
      !stickToBottomRef.current
    ) {
      return;
    }
    autoScrollFrameRef.current = window.requestAnimationFrame((timestamp) =>
      animateAutoScrollRef.current(timestamp),
    );
  }

  updateScrollbarRef.current = () => {
    const scrollContainer = scrollRef.current;
    const track = scrollbarTrackRef.current;
    const thumb = scrollbarThumbRef.current;
    if (!scrollContainer || !track || !thumb) return;

    const viewportHeight = scrollContainer.clientHeight;
    const contentHeight = scrollContainer.scrollHeight;
    const maxScroll = Math.max(0, contentHeight - viewportHeight);
    const trackHeight = track.clientHeight;
    const thumbHeight =
      maxScroll > 0
        ? Math.max(
            MIN_SCROLLBAR_THUMB_SIZE,
            Math.min(
              trackHeight,
              trackHeight * (viewportHeight / contentHeight),
            ),
          )
        : trackHeight;
    const thumbTravel = Math.max(0, trackHeight - thumbHeight);
    const thumbTop =
      maxScroll > 0
        ? thumbTravel * (scrollContainer.scrollTop / maxScroll)
        : 0;

    scrollbarMetricsRef.current = {
      maxScroll,
      thumbHeight,
      thumbTravel,
    };
    track.classList.toggle("visible", maxScroll > 1);
    track.setAttribute("aria-valuemax", String(Math.round(maxScroll)));
    track.setAttribute(
      "aria-valuenow",
      String(Math.round(scrollContainer.scrollTop)),
    );
    thumb.style.height = `${thumbHeight}px`;
    thumb.style.transform = `translate3d(0, ${thumbTop}px, 0)`;
  };

  animateAutoScrollRef.current = (timestamp: number) => {
    autoScrollFrameRef.current = null;
    const scrollContainer = scrollRef.current;
    if (
      !scrollContainer ||
      userPausedAutoScrollRef.current ||
      !stickToBottomRef.current
    ) {
      autoScrollTimestampRef.current = null;
      return;
    }

    const target = Math.max(
      0,
      scrollContainer.scrollHeight - scrollContainer.clientHeight,
    );
    const distance = target - scrollContainer.scrollTop;
    if (Math.abs(distance) <= 0.5) {
      scrollContainer.scrollTop = target;
      autoScrollTimestampRef.current = null;
      scheduleScrollbarUpdate();
      return;
    }

    const elapsed = Math.min(
      50,
      Math.max(
        0,
        timestamp -
          (autoScrollTimestampRef.current ?? timestamp - 1000 / 60),
      ),
    );
    autoScrollTimestampRef.current = timestamp;
    const progress =
      1 - Math.exp(-elapsed / AUTO_SCROLL_TIME_CONSTANT_MS);
    scrollContainer.scrollTop += distance * progress;
    scheduleScrollbarUpdate();
    autoScrollFrameRef.current = window.requestAnimationFrame(
      (nextTimestamp) => animateAutoScrollRef.current(nextTimestamp),
    );
  };

  useEffect(() => {
    scheduleScrollbarUpdate();
    startAutoScroll();
  }, [messages]);

  useEffect(() => {
    const scrollContainer = scrollRef.current;
    const messageList = messageListRef.current;
    if (!scrollContainer || !messageList) return;

    const observer = new ResizeObserver(() => {
      scheduleScrollbarUpdate();
      startAutoScroll();
    });
    observer.observe(scrollContainer);
    observer.observe(messageList);
    scheduleScrollbarUpdate();
    startAutoScroll();

    return () => {
      observer.disconnect();
      stopAutoScroll();
      if (scrollbarUpdateFrameRef.current !== null) {
        window.cancelAnimationFrame(scrollbarUpdateFrameRef.current);
        scrollbarUpdateFrameRef.current = null;
      }
    };
  }, []);

  function updateStickToBottom() {
    const scrollContainer = scrollRef.current;
    if (!scrollContainer) return;
    scheduleScrollbarUpdate();
    const distanceFromBottom =
      scrollContainer.scrollHeight -
      scrollContainer.scrollTop -
      scrollContainer.clientHeight;
    if (distanceFromBottom <= 2) {
      userPausedAutoScrollRef.current = false;
      stickToBottomRef.current = true;
      return;
    }
    if (userPausedAutoScrollRef.current) {
      stickToBottomRef.current = false;
    }
  }

  function scrollToPosition(scrollTop: number) {
    const scrollContainer = scrollRef.current;
    if (!scrollContainer) return;
    pauseAutoScroll();
    scrollContainer.scrollTop = Math.max(
      0,
      Math.min(scrollbarMetricsRef.current.maxScroll, scrollTop),
    );
    if (
      scrollbarMetricsRef.current.maxScroll - scrollContainer.scrollTop <=
      2
    ) {
      userPausedAutoScrollRef.current = false;
      stickToBottomRef.current = true;
    }
    scheduleScrollbarUpdate();
  }

  function handleScrollbarTrackPointerDown(
    event: ReactPointerEvent<HTMLDivElement>,
  ) {
    if (event.target === scrollbarThumbRef.current) return;
    const track = scrollbarTrackRef.current;
    if (!track) return;
    const { thumbHeight, thumbTravel, maxScroll } =
      scrollbarMetricsRef.current;
    if (maxScroll <= 0 || thumbTravel <= 0) return;
    const trackRect = track.getBoundingClientRect();
    const nextThumbTop = Math.max(
      0,
      Math.min(
        thumbTravel,
        event.clientY - trackRect.top - thumbHeight / 2,
      ),
    );
    scrollToPosition((nextThumbTop / thumbTravel) * maxScroll);
  }

  function handleScrollbarThumbPointerDown(
    event: ReactPointerEvent<HTMLDivElement>,
  ) {
    const scrollContainer = scrollRef.current;
    const track = scrollbarTrackRef.current;
    if (!scrollContainer || !track) return;
    event.stopPropagation();
    pauseAutoScroll();
    thumbDragRef.current = {
      pointerId: event.pointerId,
      startY: event.clientY,
      startScrollTop: scrollContainer.scrollTop,
    };
    track.classList.add("dragging");
    event.currentTarget.setPointerCapture(event.pointerId);
  }

  function handleScrollbarThumbPointerMove(
    event: ReactPointerEvent<HTMLDivElement>,
  ) {
    const drag = thumbDragRef.current;
    const { thumbTravel, maxScroll } = scrollbarMetricsRef.current;
    if (
      !drag ||
      drag.pointerId !== event.pointerId ||
      thumbTravel <= 0
    ) {
      return;
    }
    scrollToPosition(
      drag.startScrollTop +
        ((event.clientY - drag.startY) / thumbTravel) * maxScroll,
    );
    userPausedAutoScrollRef.current = true;
    stickToBottomRef.current = false;
  }

  function finishScrollbarThumbDrag(
    event: ReactPointerEvent<HTMLDivElement>,
  ) {
    if (thumbDragRef.current?.pointerId !== event.pointerId) return;
    thumbDragRef.current = null;
    scrollbarTrackRef.current?.classList.remove("dragging");
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    const scrollContainer = scrollRef.current;
    if (
      scrollContainer &&
      scrollbarMetricsRef.current.maxScroll - scrollContainer.scrollTop <= 2
    ) {
      userPausedAutoScrollRef.current = false;
      stickToBottomRef.current = true;
    }
  }

  function handleScrollbarKeyDown(
    event: ReactKeyboardEvent<HTMLDivElement>,
  ) {
    const scrollContainer = scrollRef.current;
    if (!scrollContainer) return;
    let nextScrollTop: number | null = null;
    if (event.key === "ArrowUp") {
      nextScrollTop = scrollContainer.scrollTop - 40;
    } else if (event.key === "ArrowDown") {
      nextScrollTop = scrollContainer.scrollTop + 40;
    } else if (event.key === "PageUp") {
      nextScrollTop =
        scrollContainer.scrollTop - scrollContainer.clientHeight * 0.9;
    } else if (event.key === "PageDown") {
      nextScrollTop =
        scrollContainer.scrollTop + scrollContainer.clientHeight * 0.9;
    } else if (event.key === "Home") {
      nextScrollTop = 0;
    } else if (event.key === "End") {
      nextScrollTop = scrollbarMetricsRef.current.maxScroll;
    }
    if (nextScrollTop === null) return;
    event.preventDefault();
    scrollToPosition(nextScrollTop);
  }

  return (
    <div className="chat-scroll-shell">
      <section
        className="chat-view"
        id="chat-scroll-viewport"
        aria-live="polite"
        ref={scrollRef}
        onScroll={updateStickToBottom}
        onWheel={(event) => {
          if (event.deltaY < 0) pauseAutoScroll();
        }}
      >
        <div className="message-list" ref={messageListRef}>
          {messages.map((message, index) => (
            <MessageView
              active={
                isStreaming &&
                message.role === "assistant" &&
                index === messages.length - 1
              }
              key={message.id}
              message={message}
            />
          ))}
          <div className="message-scroll-anchor" />
        </div>
      </section>
      <div
        className="chat-scrollbar"
        ref={scrollbarTrackRef}
        role="scrollbar"
        aria-controls="chat-scroll-viewport"
        aria-orientation="vertical"
        aria-valuemin={0}
        aria-valuemax={0}
        aria-valuenow={0}
        tabIndex={0}
        onKeyDown={handleScrollbarKeyDown}
        onPointerDown={handleScrollbarTrackPointerDown}
      >
        <div
          className="chat-scrollbar-thumb"
          ref={scrollbarThumbRef}
          onPointerDown={handleScrollbarThumbPointerDown}
          onPointerMove={handleScrollbarThumbPointerMove}
          onPointerUp={finishScrollbarThumbDrag}
          onPointerCancel={finishScrollbarThumbDrag}
        />
      </div>
    </div>
  );
}
