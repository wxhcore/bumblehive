import type { PendingChatMessage, ToolActivity, UiMessage, WorkerReport } from "../types/api";

const reportHeader = /^\[Background tool result\]\nTask ID: ([^\r\n]+)\n\n/;

export function workerTaskTitle(task: ToolActivity | undefined): string | undefined {
  if (task?.name !== "sub_agent") return;
  const args = task.arguments as { title?: unknown } | undefined;
  return typeof args?.title === "string" ? args.title.trim() || undefined : undefined;
}

function workerReport(content: string, tasks: ReadonlyMap<string, ToolActivity>): WorkerReport | undefined {
  const header = reportHeader.exec(content);
  if (!header) return;
  const title = workerTaskTitle(tasks.get(header[1]));
  if (title) return { title, body: content.slice(header[0].length) };
}

export function collectWorkerTasks(messages: UiMessage[]) {
  const tasks = new Map<string, ToolActivity>();
  for (const message of messages) {
    for (const iteration of message.iterations ?? []) {
      for (const tool of iteration.tools ?? []) {
        if (tool.name === "sub_agent") tasks.set(tool.taskId ?? tool.id, tool);
      }
    }
  }
  return tasks;
}

export function liveWorkerReport(input: PendingChatMessage, messages: UiMessage[]) {
  if (!input.message_id.startsWith("subagent:")) return;
  return workerReport(input.content, collectWorkerTasks(messages));
}

// Recovery can join adjacent user inputs, including several notifications, with two newlines.
export function historyInputParts(
  content: string, tasks: ReadonlyMap<string, ToolActivity>,
): Array<{ content: string; report?: WorkerReport }> {
  if (!content.includes("[Background tool result]")) return [{ content }];
  const parts = content.split(/\n\n(?=\[(?:Background tool result|Sub-agent progress update)\]\nTask ID: [^\r\n]+\n\n)/);
  const inputs: Array<{ content: string; report?: WorkerReport }> = [];
  for (const text of parts) {
    const report = workerReport(text, tasks);
    const previous = inputs.at(-1);
    // A report may itself quote the protocol. Only split off another known tool's notification.
    const header = /^\[(?:Background tool result|Sub-agent progress update)\]\nTask ID: ([^\r\n]+)\n\n/.exec(text);
    if (previous && !(header && tasks.has(header[1]))) {
      previous.content += "\n\n" + text;
      if (previous.report) previous.report.body += "\n\n" + text;
    } else {
      inputs.push({ content: text, report });
    }
  }
  return inputs.some(input => input.report) ? inputs : [{ content, report: undefined }];
}
