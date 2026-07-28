import { API_URL } from "./config";
import type {
  CreatedSession,
  HealthResponse,
  ModelListRequest,
  ModelListResponse,
  SessionDetail,
  SessionSummary,
  Settings,
  SettingsUpdate,
} from "../types/api";

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
    throw new Error(message);
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

export function updateSettings(update: SettingsUpdate): Promise<Settings> {
  return request("/api/v1/settings", jsonInit("PUT", update));
}

export function getModels(requestBody: ModelListRequest): Promise<ModelListResponse> {
  return request("/api/v1/models", jsonInit("POST", requestBody));
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
