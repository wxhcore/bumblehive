import { useState, type KeyboardEvent } from "react";
import type { UserQuestion } from "../types/api";

interface QuestionCardProps {
  question: UserQuestion;
  disconnected: boolean;
  onSkip: () => void;
  onAnswer: (question: UserQuestion, answer: string) => void;
}

export function QuestionCard({ question, disconnected, onAnswer, onSkip }: QuestionCardProps) {
  const [selected, setSelected] = useState<number | null>(null);
  const [text, setText] = useState("");
  const answer = text.trim() ? text : selected === null ? "" : question.options[selected];
  const disabled = disconnected || question.submitting;
  const submit = () => {
    if (!disabled && answer.trim()) onAnswer(question, answer);
  };
  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      event.stopPropagation();
      submit();
    }
  };

  return (
    <section className="question-card" aria-label="问题">
      <header className="question-heading">
        <span><span className="question-badge" aria-hidden="true">?</span> 问题</span>
        <button
          type="button"
          className="question-close"
          aria-label="跳过此问题"
          title="跳过此问题"
          disabled={disabled}
          onClick={onSkip}
        >×</button>
      </header>
      <p className="question-prompt">{question.question}</p>
      {question.options.length > 0 ? (
        <div className="question-options" role="group" aria-label="可选答案">
          {question.options.map((option, index) => (
            <button
              key={index}
              type="button"
              className={`question-option${selected === index && !text.trim() ? " selected" : ""}`}
              aria-pressed={selected === index && !text.trim()}
              disabled={disabled}
              onClick={() => { setSelected(index); setText(""); }}
            >
              <span className="question-number">{index + 1}</span>
              <span>{option}</span>
            </button>
          ))}
        </div>
      ) : null}
      <div className="question-reply">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m15 4 5 5M4 20l5-1L20 8a2 2 0 0 0-5-5L4 14Z" /></svg>
        <textarea
          aria-label="自由填写回答"
          placeholder={question.options.length ? "或自行撰写回复" : "请填写你的回答"}
          rows={2}
          value={text}
          disabled={disabled}
          onChange={(event) => setText(event.target.value)}
          onKeyDown={onKeyDown}
        />
        <button type="button" className="question-skip" title="跳过此问题"
          disabled={disabled} onClick={onSkip}>跳过</button>
        <button type="button" className="question-send" disabled={disabled || !answer.trim()}
          onClick={submit}>{question.submitting ? "发送中…" : "发送"}</button>
      </div>
      {question.error ? <p className="question-error" role="alert">{question.error}</p> : null}
      {disconnected ? <p className="question-hint">连接已中断，重连后可继续回答</p> : null}
    </section>
  );
}
