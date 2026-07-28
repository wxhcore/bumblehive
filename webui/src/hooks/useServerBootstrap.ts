import { useCallback, useEffect, useState } from "react";
import { getHealth, getSessions, getSettings } from "../api/http";
import type { SessionSummary, Settings } from "../types/api";
import { useStableCallback } from "./useStableCallback";

export type BootstrapStatus = "loading" | "ready" | "error";

interface UseServerBootstrapOptions {
  onReady: (settings: Settings, sessions: SessionSummary[]) => void;
}

const wait = (milliseconds: number) =>
  new Promise((resolve) => window.setTimeout(resolve, milliseconds));

export function useServerBootstrap({
  onReady,
}: UseServerBootstrapOptions) {
  const [status, setStatus] = useState<BootstrapStatus>("loading");
  const [attempt, setAttempt] = useState(0);
  const handleReady = useStableCallback(onReady);

  useEffect(() => {
    let cancelled = false;

    async function bootstrap() {
      setStatus("loading");
      let connected = false;
      for (let index = 0; index < 12 && !cancelled; index += 1) {
        try {
          const health = await getHealth();
          if (health.status === "ok" && health.runtime === "ready") {
            connected = true;
            break;
          }
        } catch {
          // The Tauri sidecar may still be starting.
        }
        await wait(500);
      }

      if (!connected || cancelled) {
        if (!cancelled) setStatus("error");
        return;
      }

      try {
        const [settings, sessions] = await Promise.all([
          getSettings(),
          getSessions(),
        ]);
        if (cancelled) return;
        handleReady(settings, sessions);
        setStatus("ready");
      } catch {
        if (!cancelled) setStatus("error");
      }
    }

    void bootstrap();
    return () => {
      cancelled = true;
    };
  }, [attempt, handleReady]);

  const retry = useCallback(() => {
    setAttempt((current) => current + 1);
  }, []);

  return { retry, status };
}
