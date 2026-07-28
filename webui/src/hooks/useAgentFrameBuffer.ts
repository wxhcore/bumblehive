import { useCallback, useEffect, useRef } from "react";
import {
  appendPendingAgentFrame,
  applyAgentEventFrames,
  streamedDelta,
  takeAgentFramesForPaint,
} from "../lib/chat-events";
import type { AgentEventFrame, UiMessage } from "../types/api";

const STREAM_CATCH_UP_MS = 72;
const MIN_STREAM_CHARACTERS_PER_SECOND = 90;
const MAX_STREAM_FRAME_ELAPSED_MS = 50;

interface UseAgentFrameBufferOptions {
  getAssistantId: (sessionId: string) => string | undefined;
  updateSessionMessages: (
    sessionId: string,
    update: (current: UiMessage[]) => UiMessage[],
  ) => void;
}

export function useAgentFrameBuffer({
  getAssistantId,
  updateSessionMessages,
}: UseAgentFrameBufferOptions) {
  const pendingFramesRef = useRef(
    new Map<string, AgentEventFrame[]>(),
  );
  const paintStateRef = useRef(
    new Map<string, { credit: number; lastTimestamp: number | null }>(),
  );
  const animationRef = useRef<number | null>(null);
  const paintRef = useRef<(timestamp: number) => void>(() => undefined);

  const schedulePaint = useCallback(() => {
    if (animationRef.current !== null) return;
    animationRef.current = window.requestAnimationFrame((timestamp) => {
      animationRef.current = null;
      paintRef.current(timestamp);
    });
  }, []);

  const flush = useCallback(
    (sessionId?: string) => {
      const queued: Array<[string, AgentEventFrame[]]> = [];
      if (sessionId) {
        const frames = pendingFramesRef.current.get(sessionId);
        if (frames?.length) {
          pendingFramesRef.current.delete(sessionId);
          queued.push([sessionId, frames]);
        }
      } else {
        queued.push(...pendingFramesRef.current);
        pendingFramesRef.current.clear();
      }

      if (
        pendingFramesRef.current.size === 0 &&
        animationRef.current !== null
      ) {
        window.cancelAnimationFrame(animationRef.current);
        animationRef.current = null;
      }

      for (const [queuedSessionId, frames] of queued) {
        paintStateRef.current.delete(queuedSessionId);
        const assistantId = getAssistantId(queuedSessionId);
        if (!assistantId) continue;
        updateSessionMessages(queuedSessionId, (current) =>
          applyAgentEventFrames(current, assistantId, frames),
        );
      }
    },
    [getAssistantId, updateSessionMessages],
  );

  const paint = useCallback(
    (timestamp: number) => {
      for (const [sessionId, frames] of pendingFramesRef.current) {
        const assistantId = getAssistantId(sessionId);
        if (!assistantId) {
          pendingFramesRef.current.delete(sessionId);
          paintStateRef.current.delete(sessionId);
          continue;
        }

        const paintState = paintStateRef.current.get(sessionId) ?? {
          credit: 0,
          lastTimestamp: null,
        };
        const elapsed = Math.min(
          MAX_STREAM_FRAME_ELAPSED_MS,
          Math.max(
            0,
            timestamp - (paintState.lastTimestamp ?? timestamp),
          ),
        );
        const textBacklog = frames.reduce(
          (total, frame) => total + (streamedDelta(frame)?.length ?? 0),
          0,
        );
        const charactersPerSecond = Math.max(
          MIN_STREAM_CHARACTERS_PER_SECOND,
          (textBacklog * 1000) / STREAM_CATCH_UP_MS,
        );
        paintState.credit += charactersPerSecond * (elapsed / 1000);
        paintState.lastTimestamp = timestamp;

        const textBudget = Math.floor(paintState.credit);
        const { painted, textCount } = takeAgentFramesForPaint(
          frames,
          textBudget,
        );
        paintState.credit = Math.max(0, paintState.credit - textCount);

        if (frames.length === 0) {
          pendingFramesRef.current.delete(sessionId);
          paintStateRef.current.delete(sessionId);
        } else {
          paintStateRef.current.set(sessionId, paintState);
        }
        if (painted.length > 0) {
          updateSessionMessages(sessionId, (current) =>
            applyAgentEventFrames(current, assistantId, painted),
          );
        }
      }

      if (pendingFramesRef.current.size > 0) {
        schedulePaint();
      }
    },
    [getAssistantId, schedulePaint, updateSessionMessages],
  );
  paintRef.current = paint;

  const queue = useCallback(
    (sessionId: string, frame: AgentEventFrame) => {
      const pending = pendingFramesRef.current.get(sessionId);
      if (pending) appendPendingAgentFrame(pending, frame);
      else pendingFramesRef.current.set(sessionId, [frame]);
      schedulePaint();
    },
    [schedulePaint],
  );

  const forget = useCallback((sessionIds: Iterable<string>) => {
    for (const sessionId of sessionIds) {
      pendingFramesRef.current.delete(sessionId);
      paintStateRef.current.delete(sessionId);
    }
  }, []);

  useEffect(
    () => () => {
      if (animationRef.current !== null) {
        window.cancelAnimationFrame(animationRef.current);
      }
      pendingFramesRef.current.clear();
      paintStateRef.current.clear();
    },
    [],
  );

  return { flush, forget, queue };
}
