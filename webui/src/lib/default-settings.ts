export const DEFAULT_CONFIG_VALUES = {
  provider: {
    type: "openai_chat_completions",
  },
  generation: {
    maxCompletionTokens: 16_384,
  },
  runtime: {
    contextWindowTokens: 200_000,
    maxToolResultChars: 20_000,
    maxIterations: 300,
    restrictExecPaths: false,
  },
} as const;

export function detectSystemTimeZone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "";
  } catch {
    return "";
  }
}
