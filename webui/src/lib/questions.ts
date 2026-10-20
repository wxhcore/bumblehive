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
      question_id: frame.question_id,
      question: frame.question,
      options: frame.options,
    };
    return [
      ...questions.filter((q) => q.session_id !== sessionId || q.question_id !== item.question_id),
      item,
    ];
  }
  if (frame.type === "question_closed") {
    return questions.filter((item) =>
      item.session_id !== sessionId || item.question_id !== frame.question_id,
    );
  }
  if (frame.type === "error" && frame.scope === "input" && frame.question_id) {
    return questions.map((item) =>
      item.session_id === sessionId && item.question_id === frame.question_id
        ? { ...item, submitting: false, error: frame.message }
        : item,
    );
  }
  return questions;
}
