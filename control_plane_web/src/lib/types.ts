export interface ProjectSummary {
  id: string;
  name: string;
  source_type: string;
  source_uri_or_path: string;
  source_lang: string;
  target_lang: string;
  status: 'draft' | 'processing' | 'review_required' | 'failed' | 'completed' | 'archived';
  progress_pct: number;
  current_stage: string | null;
  current_step: string | null;
  cover_path: string | null;
  created_at: string;
  updated_at: string;
}

export interface EffectiveSetting {
  value: string | boolean | number | null;
  source: 'global' | 'global_override' | 'project_override';
}

export interface WorkflowStep {
  step_id: string;
  title: string;
  depends_on: string[];
  artifact_patterns: string[];
  preview_patterns: string[];
}

export interface WorkflowStage {
  stage_id: string;
  steps: WorkflowStep[];
}

export interface WorkspaceResponse {
  project: ProjectSummary;
  stages: WorkflowStage[];
  effective_settings: Record<string, EffectiveSetting>;
  latest_run_id: string | null;
}

export interface SubtitleReviewRow {
  row_id: string;
  start: string;
  end: string;
  source_text: string;
  target_text: string;
}

export interface SubtitleReviewPayload {
  rows: SubtitleReviewRow[];
}

export interface GlobalSettingsResponse {
  global: Record<string, unknown>;
}

export interface RunSummary {
  id: string;
  project_id: string;
  status: string;
  started_at: string;
}

export interface RunNode {
  step_id: string;
  stage_id: string;
  status: string;
  title: string;
  artifact_patterns: string[];
  depends_on: string[];
  log_excerpt: string | null;
  error_summary: string | null;
}

export interface RunNodesResponse {
  run_id: string;
  nodes: RunNode[];
}

export interface RunArtifactGroup {
  step_id: string;
  stage_id: string;
  files: string[];
}

export interface RunArtifactsResponse {
  run_id: string;
  artifacts: RunArtifactGroup[];
}

export interface LogEntry {
  name: string;
  content: string;
  source: string;
}

export interface RunLogsResponse {
  run_id: string;
  logs: LogEntry[];
}
