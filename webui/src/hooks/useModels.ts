import {
  useCallback,
  useMemo,
  useRef,
  useState,
  type Dispatch,
  type SetStateAction,
} from "react";
import { getModels, updateSettings } from "../api/http";
import type { Settings } from "../types/api";

interface UseModelsOptions {
  settings: Settings | null;
  setSettings: Dispatch<SetStateAction<Settings | null>>;
  hasRunningSessions: boolean;
  notify: (message: string) => void;
}

export function useModels({
  settings,
  setSettings,
  hasRunningSessions,
  notify,
}: UseModelsOptions) {
  const [availableModels, setAvailableModels] = useState<string[]>([]);
  const [switching, setSwitching] = useState(false);
  const requestIdRef = useRef(0);

  const load = useCallback(async (currentSettings: Settings) => {
    const requestId = ++requestIdRef.current;
    const baseUrl = currentSettings.provider.base_url?.trim();
    setAvailableModels([]);
    if (!baseUrl) return;
    try {
      const response = await getModels({ base_url: baseUrl });
      if (requestId !== requestIdRef.current) return;
      setAvailableModels(
        Array.from(
          new Set(
            response.models
              .map((model) => model.trim())
              .filter((model) => Boolean(model)),
          ),
        ),
      );
    } catch {
      if (requestId === requestIdRef.current) {
        setAvailableModels([]);
      }
    }
  }, []);

  const select = useCallback(
    async (selectedModel: string) => {
      if (
        !settings ||
        selectedModel === settings.provider.model ||
        hasRunningSessions ||
        switching
      ) {
        return;
      }
      setSwitching(true);
      try {
        const saved = await updateSettings({
          provider: {
            model: selectedModel,
          },
        });
        setSettings(saved);
        notify(`已切换到 ${selectedModel}`);
      } catch (error) {
        notify(error instanceof Error ? error.message : "模型切换失败");
      } finally {
        setSwitching(false);
      }
    },
    [hasRunningSessions, notify, setSettings, settings, switching],
  );

  const selectable = useMemo(
    () =>
      settings
        ? Array.from(
            new Set(
              [settings.provider.model, ...availableModels].filter(
                (model): model is string => Boolean(model),
              ),
            ),
          )
        : [],
    [availableModels, settings],
  );

  return {
    load,
    select,
    selectable,
    switching,
  };
}
