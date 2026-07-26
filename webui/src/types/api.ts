export interface HealthResponse {
  status: string;
  runtime: "ready" | "unavailable";
}

interface ProviderSettings {
  type: string;
  model?: string | null;
  base_url?: string | null;
  api_key_configured: boolean;
}

interface GenerationSettings {
  max_completion_tokens?: number | null;
  temperature?: number | null;
  reasoning_effort?: string | null;
  extra_body?: Record<string, unknown> | null;
}

interface AgentSettings {
  instructions?: string | null;
  dynamic_context?: Record<string, unknown>;
  skill_names?: string[] | null;
  tool_names?: string[] | null;
}

interface RuntimeSettings {
  workspace?: string | null;
  timezone?: string | null;
  context_window_tokens?: number | null;
  max_tool_result_chars?: number | null;
  max_iterations?: number | null;
  extra_read_roots?: string[];
  extra_write_roots?: string[];
}

export interface Settings {
  provider: ProviderSettings;
  generation: GenerationSettings;
  agent?: AgentSettings;
  runtime?: RuntimeSettings;
  mcp_servers?: Array<Record<string, unknown>>;
}

export type SettingsUpdate = Record<string, unknown>;

export interface ModelListRequest {
  base_url: string;
  api_key?: string;
}

export interface ModelListResponse {
  models: string[];
}

export interface SessionSummary {
  session_id: string;
  workspace: string;
  message_count: number;
  title: string;
  last_message: string;
  created_at: number;
  updated_at: number;
}

export interface StoredMessage {
  role?: string;
  content?: unknown;
  [key: string]: unknown;
}

export interface SessionDetail {
  session_id: string;
  workspace: string;
  messages: StoredMessage[];
  created_at: number;
  updated_at: number;
}

export interface CreatedSession {
  session_id: string;
  workspace: string;
}

export interface AgentEventFrame {
  type: "event";
  kind: string;
  run_id: string;
  payload: Record<string, unknown>;
  iteration: number | null;
  session_id: string | null;
  timestamp: number;
}

export interface ReadyFrame {
  type: "ready";
  session_id: string;
}

export interface ResultFrame {
  type: "result";
  final_content: string | null;
  tools_used: string[];
  usage: Record<string, number>;
  stop_reason: string;
  error: { code: string; message: string; recoverable: boolean } | null;
}

export interface ErrorFrame {
  type: "error";
  code: string;
  message: string;
}

export interface CancelledFrame {
  type: "cancelled";
  session_id: string;
}

export type ChatFrame =
  | ReadyFrame
  | AgentEventFrame
  | ResultFrame
  | ErrorFrame
  | CancelledFrame;

export type ToolActivityStatus =
  | "preparing"
  | "running"
  | "completed"
  | "cancelled"
  | "error";

export interface ToolActivity {
  id: string;
  name: string;
  arguments?: unknown;
  streamedArguments?: string;
  streamIndex?: number;
  status: ToolActivityStatus;
  durationSeconds?: number;
  errorMessage?: string;
}

export interface AssistantIteration {
  id: string;
  iteration: number | null;
  reasoning?: string;
  content: string;
  tools?: ToolActivity[];
}

export interface UiMessage {
  id: string;
  role: "user" | "assistant" | "tool";
  content: string;
  iterations?: AssistantIteration[];
  startedAt?: number;
  durationSeconds?: number;
  stopped?: boolean;
  error?: boolean;
}
