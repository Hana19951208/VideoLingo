import type {
  GlobalSettingsResponse,
  ProjectSummary,
  RunArtifactsResponse,
  RunLogsResponse,
  RunNodesResponse,
  RunSummary,
  SubtitleReviewPayload,
  WorkspaceResponse,
} from './types';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
    ...init,
  });

  if (!response.ok) {
    const text = await response.text();
    let message = text || `Request failed: ${response.status}`;
    try {
      const payload = JSON.parse(text) as { detail?: string };
      message = payload.detail || message;
    } catch {
      // Ignore JSON parse errors and fall back to raw response text.
    }
    throw new Error(message);
  }

  return response.json() as Promise<T>;
}

export const api = {
  baseUrl: API_BASE_URL,
  listProjects: () => request<ProjectSummary[]>('/projects'),
  createProject: (payload: {
    name: string;
    source_type: string;
    source_uri_or_path: string;
    source_lang: string;
    target_lang: string;
  }) => request<ProjectSummary>('/projects', { method: 'POST', body: JSON.stringify(payload) }),
  getProject: (projectId: string) => request<ProjectSummary>(`/projects/${projectId}`),
  getWorkspace: (projectId: string) => request<WorkspaceResponse>(`/projects/${projectId}/workspace`),
  startRun: (projectId: string) => request<RunSummary>(`/projects/${projectId}/runs`, { method: 'POST' }),
  runAction: (runId: string, payload: { action: string; stage_id?: string; step_id?: string }) =>
    request<{ run_id: string; accepted: boolean; action: string }>(`/runs/${runId}/actions`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  getRunNodes: (runId: string) => request<RunNodesResponse>(`/runs/${runId}/nodes`),
  getRunArtifacts: (runId: string) => request<RunArtifactsResponse>(`/runs/${runId}/artifacts`),
  getRunLogs: (runId: string) => request<RunLogsResponse>(`/runs/${runId}/logs`),
  getSettings: () => request<GlobalSettingsResponse>('/settings'),
  updateSettings: (payload: { project_id?: number; overrides: Record<string, unknown> }) =>
    request<{ scope: string; updated_keys?: string[]; project_id?: number; overrides?: Record<string, unknown> }>('/settings', {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),
  getSubtitleReview: (projectId: string) => request<SubtitleReviewPayload>(`/projects/${projectId}/subtitle-review`),
  saveSubtitleReview: (projectId: string, payload: SubtitleReviewPayload) =>
    request<SubtitleReviewPayload>(`/projects/${projectId}/subtitle-review`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),
  getArtifactUrl: (path: string) => `${API_BASE_URL}/artifacts/file?path=${encodeURIComponent(path)}`,
};
