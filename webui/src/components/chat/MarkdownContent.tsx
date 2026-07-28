import { memo, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

const MARKDOWN_PLUGINS = [remarkGfm];

interface ReasoningBlockProps {
  content: string;
  active: boolean;
  defaultOpen?: boolean;
  streaming?: boolean;
}

export const StreamedMarkdown = memo(function StreamedMarkdown({
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

export const ReasoningBlock = memo(function ReasoningBlock({
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
