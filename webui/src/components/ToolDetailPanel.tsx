import { memo, useState } from "react";
import type {
  MutationToolDetail,
  ShellSessionsToolDetail,
  ShellToolDetail,
  ToolActivity,
} from "../types/api";
import { textLines } from "../text-lines";

const MAX_DIFF_ROWS = 420;
const MAX_DIFF_LINE_CHARACTERS = 4_000;

interface DiffFile {
  path: string;
  oldText: string;
  newText: string;
  added: number;
  deleted: number;
  startLine?: number;
}

interface DiffRow {
  kind: "addition" | "deletion" | "omitted";
  lineNumber: number | null;
  text: string;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value !== null &&
    typeof value === "object" &&
    !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function textValue(
  record: Record<string, unknown> | null,
  key: string,
): string {
  return typeof record?.[key] === "string" ? record[key] : "";
}

function mutationFiles(tool: ToolActivity): DiffFile[] {
  const argumentsValue = asRecord(tool.arguments);
  const detail =
    tool.detail?.kind === "mutation" ? tool.detail : undefined;

  if (tool.name === "write_file") {
    const path = (
      textValue(argumentsValue, "path") ||
      detail?.path ||
      "新文件"
    ).slice(0, 1_000);
    const newText = textValue(argumentsValue, "content");
    return [
      {
        path,
        oldText: "",
        newText,
        added: textLines(newText).length,
        deleted: 0,
      },
    ];
  }

  if (tool.name === "edit_file") {
    const path = (
      textValue(argumentsValue, "path") ||
      detail?.path ||
      "文件"
    ).slice(0, 1_000);
    const oldText = textValue(argumentsValue, "old_text");
    const newText = textValue(argumentsValue, "new_text");
    const rawStartLine = argumentsValue?.line_hint;
    return [
      {
        path,
        oldText,
        newText,
        added: textLines(newText).length,
        deleted: textLines(oldText).length,
        startLine:
          typeof rawStartLine === "number" && Number.isFinite(rawStartLine)
            ? rawStartLine
            : undefined,
      },
    ];
  }

  if (tool.name !== "apply_patch" || !Array.isArray(argumentsValue?.edits)) {
    return [];
  }

  const summaries = new Map(
    (detail?.edits ?? []).map((edit) => [edit.path, edit]),
  );
  return argumentsValue.edits.flatMap((rawEdit) => {
    const edit = asRecord(rawEdit);
    const path = textValue(edit, "path").slice(0, 1_000);
    if (!edit || !path) return [];
    const action = textValue(edit, "action");
    const oldText = action === "add" ? "" : textValue(edit, "old_text");
    const newText = textValue(edit, "new_text");
    const summary = summaries.get(path);
    return [
      {
        path,
        oldText,
        newText,
        added: summary?.added ?? textLines(newText).length,
        deleted: summary?.deleted ?? textLines(oldText).length,
      },
    ];
  });
}

function diffRows(file: DiffFile): DiffRow[] {
  const rows: DiffRow[] = [];
  const startLine = file.startLine ?? 1;
  textLines(file.oldText).forEach((text, index) => {
    rows.push({
      kind: "deletion",
      lineNumber: startLine + index,
      text:
        text.length > MAX_DIFF_LINE_CHARACTERS
          ? `${text.slice(0, MAX_DIFF_LINE_CHARACTERS)}…`
          : text,
    });
  });
  textLines(file.newText).forEach((text, index) => {
    rows.push({
      kind: "addition",
      lineNumber: startLine + index,
      text:
        text.length > MAX_DIFF_LINE_CHARACTERS
          ? `${text.slice(0, MAX_DIFF_LINE_CHARACTERS)}…`
          : text,
    });
  });
  if (rows.length <= MAX_DIFF_ROWS) return rows;

  const head = rows.slice(0, MAX_DIFF_ROWS - 80);
  const tail = rows.slice(-79);
  return [
    ...head,
    {
      kind: "omitted",
      lineNumber: null,
      text: `已省略 ${rows.length - head.length - tail.length} 行`,
    },
    ...tail,
  ];
}

function displayName(path: string): string {
  return path.split(/[\\/]/).filter(Boolean).at(-1) || path;
}

function copyPath(path: string): void {
  void navigator.clipboard?.writeText(path);
}

const FileDiffCard = memo(function FileDiffCard({
  file,
  defaultOpen,
}: {
  file: DiffFile;
  defaultOpen: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const rows = open ? diffRows(file) : [];

  return (
    <section className={`tool-diff-file${open ? " open" : ""}`}>
      <div className="tool-diff-file-header">
        <button
          className="tool-diff-file-toggle"
          type="button"
          aria-expanded={open}
          onClick={() => setOpen((current) => !current)}
          title={file.path}
        >
          <span className="tool-diff-file-name">{displayName(file.path)}</span>
          <span className="tool-diff-stats" aria-label="修改行数">
            {file.added ? (
              <span className="tool-diff-added">+{file.added}</span>
            ) : null}
            {file.deleted ? (
              <span className="tool-diff-deleted">−{file.deleted}</span>
            ) : null}
          </span>
          <span
            className={`tool-detail-chevron${open ? " open" : ""}`}
            aria-hidden="true"
          />
        </button>
        <button
          className="tool-copy-path"
          type="button"
          aria-label={`复制 ${file.path}`}
          title="复制文件路径"
          onClick={() => copyPath(file.path)}
        >
          <span aria-hidden="true" />
        </button>
      </div>
      {open ? (
        <div className="tool-diff-code" role="region" aria-label={file.path}>
          {rows.length ? (
            rows.map((row, index) => (
              <div
                className={`tool-diff-row tool-diff-${row.kind}`}
                key={`${row.kind}-${row.lineNumber ?? "more"}-${index}`}
              >
                <span className="tool-diff-gutter" aria-hidden="true">
                  {row.kind === "addition"
                    ? "+"
                    : row.kind === "deletion"
                      ? "−"
                      : "⋯"}
                </span>
                <span className="tool-diff-line-number" aria-hidden="true">
                  {row.lineNumber ?? ""}
                </span>
                <code>{row.text || " "}</code>
              </div>
            ))
          ) : (
            <div className="tool-detail-empty">没有可展示的文本差异</div>
          )}
        </div>
      ) : null}
    </section>
  );
});

function ShellDetail({ detail, tool }: {
  detail: ShellToolDetail;
  tool: ToolActivity;
}) {
  const argumentsValue = asRecord(tool.arguments);
  const command = (
    detail.command || textValue(argumentsValue, "command")
  ).slice(0, 4_000);
  const output = detail.output || detail.stdout;
  const exitLabel =
    detail.running || detail.done === false
      ? "运行中"
      : detail.timedOut
        ? "已超时"
        : detail.terminated
          ? "已停止"
          : detail.exitCode !== undefined && detail.exitCode !== null
            ? `exit ${detail.exitCode}`
            : "";

  return (
    <div className="tool-shell-card">
      <div className="tool-detail-card-header">
        <span>Shell</span>
        <span className="tool-shell-exit">{exitLabel}</span>
      </div>
      {detail.workingDirectory ? (
        <div className="tool-shell-directory" title={detail.workingDirectory}>
          {detail.workingDirectory}
        </div>
      ) : null}
      {command ? (
        <div className="tool-shell-command">
          <span aria-hidden="true">$</span>
          <code>{command}</code>
        </div>
      ) : null}
      <div className="tool-shell-output">
        {output ? <pre>{output}</pre> : null}
        {detail.stderr ? <pre>{detail.stderr}</pre> : null}
        {!output && !detail.stderr ? (
          <div className="tool-detail-empty">
            {detail.running || detail.done === false
              ? "正在等待命令输出…"
              : "命令没有输出"}
          </div>
        ) : null}
      </div>
      {detail.truncatedCharacters > 0 ? (
        <div className="tool-detail-footnote">
          为保持流畅，已省略 {detail.truncatedCharacters} 个字符
        </div>
      ) : null}
    </div>
  );
}

function formatSessionDuration(seconds: number | undefined): string {
  if (seconds === undefined) return "";
  const rounded = Math.max(0, Math.round(seconds));
  if (rounded < 60) return `${rounded}s`;
  const minutes = Math.floor(rounded / 60);
  const remainingSeconds = rounded % 60;
  return remainingSeconds
    ? `${minutes}m ${remainingSeconds}s`
    : `${minutes}m`;
}

function ShellSessionsDetail({
  detail,
}: {
  detail: ShellSessionsToolDetail;
}) {
  return (
    <div className="tool-shell-sessions-card">
      <div className="tool-detail-card-header">
        <span>Shell 会话</span>
        <span>{detail.sessions.length} 个活动会话</span>
      </div>
      {detail.sessions.length ? (
        <div className="tool-shell-sessions">
          {detail.sessions.map((session) => {
            const elapsed = formatSessionDuration(session.elapsedSeconds);
            const remaining =
              session.remainingSeconds === null
                ? "无超时限制"
                : session.remainingSeconds === undefined
                  ? ""
                  : `剩余 ${formatSessionDuration(
                      session.remainingSeconds,
                    )}`;
            return (
              <section
                className="tool-shell-session"
                key={session.sessionId}
              >
                <div className="tool-shell-session-heading">
                  <span
                    className={`tool-shell-session-dot${
                      session.running ? " running" : ""
                    }`}
                    aria-hidden="true"
                  />
                  <code title={session.command}>
                    {session.command || "Shell 命令"}
                  </code>
                  <span>
                    {session.running
                      ? "运行中"
                      : session.exitCode === null ||
                          session.exitCode === undefined
                        ? "已结束"
                        : `exit ${session.exitCode}`}
                  </span>
                </div>
                {session.workingDirectory ? (
                  <div
                    className="tool-shell-session-directory"
                    title={session.workingDirectory}
                  >
                    {session.workingDirectory}
                  </div>
                ) : null}
                <div className="tool-shell-session-meta">
                  <code title={session.sessionId}>{session.sessionId}</code>
                  {elapsed ? <span>已运行 {elapsed}</span> : null}
                  {remaining ? <span>{remaining}</span> : null}
                </div>
              </section>
            );
          })}
        </div>
      ) : (
        <div className="tool-detail-empty">没有活动中的 Shell 会话</div>
      )}
    </div>
  );
}

function MutationDetail({
  detail,
  tool,
}: {
  detail: MutationToolDetail;
  tool: ToolActivity;
}) {
  const files = mutationFiles(tool);
  return (
    <div className="tool-mutation-card">
      {detail.dryRun ? (
        <div className="tool-detail-notice">仅预览，文件尚未写入</div>
      ) : null}
      {files.map((file, index) => (
        <FileDiffCard
          defaultOpen={files.length === 1 || index === 0}
          file={file}
          key={`${file.path}-${index}`}
        />
      ))}
      {!files.length ? (
        <div className="tool-detail-empty">文件已更新，没有可展示的文本差异</div>
      ) : null}
      {detail.warning ? (
        <div className="tool-detail-warning">{detail.warning}</div>
      ) : null}
    </div>
  );
}

export function hasExpandableToolDetail(tool: ToolActivity): boolean {
  if (
    tool.detail?.kind === "shell" ||
    tool.detail?.kind === "shellSessions" ||
    tool.name === "exec" ||
    tool.name === "write_stdin" ||
    tool.name === "list_exec_sessions"
  ) {
    return true;
  }
  return (
    tool.detail?.kind === "mutation" ||
    tool.name === "write_file" ||
    tool.name === "edit_file" ||
    tool.name === "apply_patch"
  );
}

export const ToolDetailPanel = memo(function ToolDetailPanel({
  tool,
}: {
  tool: ToolActivity;
}) {
  if (tool.detail?.kind === "shell") {
    return <ShellDetail detail={tool.detail} tool={tool} />;
  }
  if (tool.detail?.kind === "shellSessions") {
    return <ShellSessionsDetail detail={tool.detail} />;
  }
  if (tool.name === "list_exec_sessions") {
    return (
      <ShellSessionsDetail
        detail={{ kind: "shellSessions", sessions: [] }}
      />
    );
  }
  if (tool.name === "exec" || tool.name === "write_stdin") {
    const running =
      tool.status === "running" || tool.status === "preparing";
    return (
      <ShellDetail
        detail={{
          kind: "shell",
          output: "",
          stdout: "",
          stderr: "",
          running,
          done: !running,
          truncatedCharacters: 0,
        }}
        tool={tool}
      />
    );
  }
  if (
    tool.detail?.kind === "mutation" ||
    tool.name === "write_file" ||
    tool.name === "edit_file" ||
    tool.name === "apply_patch"
  ) {
    const detail: MutationToolDetail =
      tool.detail?.kind === "mutation"
        ? tool.detail
        : { kind: "mutation" };
    return <MutationDetail detail={detail} tool={tool} />;
  }
  return null;
});

export function mergeShellDetails(
  current: ShellToolDetail,
  next: ShellToolDetail,
): ShellToolDetail {
  const output = [current.output || current.stdout, next.output || next.stdout]
    .filter(Boolean)
    .join("");
  return {
    ...current,
    ...next,
    command: current.command || next.command,
    workingDirectory:
      current.workingDirectory || next.workingDirectory,
    output,
    stdout: "",
    stderr: [current.stderr, next.stderr].filter(Boolean).join(""),
    truncatedCharacters:
      current.truncatedCharacters + next.truncatedCharacters,
  };
}

export function shellSessionId(tool: ToolActivity): string | undefined {
  if (tool.detail?.kind === "shell" && tool.detail.sessionId) {
    return tool.detail.sessionId;
  }
  const argumentsValue = asRecord(tool.arguments);
  return typeof argumentsValue?.session_id === "string"
    ? argumentsValue.session_id
    : undefined;
}
