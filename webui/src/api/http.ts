import { API_URL } from "./config";
import type {
  CreatedSession,
  HealthResponse,
  McpServerTestRequest,
  McpServerTestResponse,
  ModelListRequest,
  ModelListResponse,
  SessionDetail,
  SessionSummary,
  Settings,
  SettingsOptions,
  SettingsUpdate,
} from "../types/api";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, init);
  if (!response.ok) {
    let message = `请求失败（${response.status}）`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) message = body.detail;
    } catch {
      // Keep the status-based message when the response is not JSON.
    }
    throw new ApiError(message, response.status);
  }
  return (await response.json()) as T;
}

function jsonInit(method: string, body: unknown): RequestInit {
  return {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
}

export function getHealth(): Promise<HealthResponse> {
  return request("/api/v1/health");
}

export function getSettings(): Promise<Settings> {
  return request("/api/v1/settings");
}

export function getSettingsOptions(): Promise<SettingsOptions> {
  return request("/api/v1/settings/options");
}

export function updateSettings(update: SettingsUpdate): Promise<Settings> {
  return request("/api/v1/settings", jsonInit("PUT", update));
}

export function getModels(requestBody: ModelListRequest): Promise<ModelListResponse> {
  return request("/api/v1/models", jsonInit("POST", requestBody));
}

export function testMcpServer(
  requestBody: McpServerTestRequest,
): Promise<McpServerTestResponse> {
  return request("/api/v1/mcp/test", jsonInit("POST", requestBody));
}

export function refreshMcpServers(): Promise<SettingsOptions> {
  return request("/api/v1/mcp/refresh", { method: "POST" });
}

export function refreshMcpServer(name: string): Promise<SettingsOptions> {
  return request(
    `/api/v1/mcp/${encodeURIComponent(name)}/refresh`,
    { method: "POST" },
  );
}

export function refreshSkills(): Promise<SettingsOptions> {
  return request("/api/v1/skills/refresh", { method: "POST" });
}

export function importSkillArchives(
  files: File[],
  replace = false,
): Promise<SettingsOptions> {
  const body = new FormData();
  files.forEach((file) => body.append("files", file, file.name));
  return request(
    `/api/v1/skills/import?replace=${replace ? "true" : "false"}`,
    {
      method: "POST",
      body,
    },
  );
}

export function deleteSkill(name: string): Promise<SettingsOptions> {
  return request(
    `/api/v1/skills/${encodeURIComponent(name)}`,
    { method: "DELETE" },
  );
}

export async function createSession(
  workspace?: string | null,
): Promise<CreatedSession> {
  const targetWorkspace = workspace?.trim();
  return request<CreatedSession>(
    "/api/v1/sessions",
    targetWorkspace
      ? jsonInit("POST", { workspace: targetWorkspace })
      : { method: "POST" },
  );
}

export async function getSessions(): Promise<SessionSummary[]> {
  const response = await request<{ sessions: SessionSummary[] }>(
    "/api/v1/sessions",
  );
  return response.sessions;
}

export function getSession(sessionId: string): Promise<SessionDetail> {
  return request(`/api/v1/sessions/${encodeURIComponent(sessionId)}`);
}

export async function deleteSession(sessionId: string): Promise<string[]> {
  const response = await request<{
    deleted: boolean;
    deleted_session_ids: string[];
  }>(
    `/api/v1/sessions/${encodeURIComponent(sessionId)}`,
    { method: "DELETE" },
  );
  return response.deleted_session_ids;
}
