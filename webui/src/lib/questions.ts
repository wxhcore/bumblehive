import type { ChatFrame, UserQuestion } from "../types/api";

export function applyQuestionFrame(
  questions: UserQuestion[],
  sessionId: string,
  frame: ChatFrame,
): UserQuestion[] {
  if (frame.type === "ready") {
    return [
      ...questions.filter((item) => item.session_id !== sessionId),
      ...(frame.questions ?? [])
        .map((item) => ({ ...item, session_id: sessionId })),
    ];
  }
  if (frame.type === "question_request") {
    const item: UserQuestion = {
      session_id: sessionId,
      task_id: frame.task_id,
      question: frame.question,
      options: frame.options,
    };
    return [
      ...questions.filter((q) => q.session_id !== sessionId || q.task_id !== item.task_id),
      item,
    ];
  }
  if (frame.type === "question_closed") {
    return questions.filter((item) =>
      item.session_id !== sessionId || item.task_id !== frame.task_id,
    );
  }
  if (frame.type === "error" && frame.scope === "input" && frame.task_id) {
    return questions.map((item) =>
      item.session_id === sessionId && item.task_id === frame.task_id
        ? { ...item, submitting: false, error: frame.message }
        : item,
    );
  }
  return questions;
}
