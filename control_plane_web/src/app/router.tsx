import { QueryClientProvider, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { FormEvent, useEffect, useMemo, useState } from 'react';
import { Link, NavLink, Outlet, Route, Routes, useNavigate, useParams } from 'react-router-dom';

import { queryClient } from './query-client';
import { api } from '../lib/api';
import type { SubtitleReviewRow, WorkspaceResponse } from '../lib/types';

const STATUS_LABELS: Record<string, string> = {
  draft: '未开始',
  processing: '处理中',
  review_required: '待字幕审阅',
  failed: '失败',
  completed: '已完成',
  archived: '已归档',
  pending: '未开始',
  running: '运行中',
  skipped: '已跳过',
};

const SETTING_FIELDS = [
  { key: 'target_language', label: '目标语言', type: 'text' },
  { key: 'whisper.runtime', label: 'Whisper 运行环境', type: 'select', options: ['local', 'cloud'] },
  { key: 'demucs', label: '启用 Demucs', type: 'boolean' },
  { key: 'tts_method', label: 'TTS 方法', type: 'select', options: ['edge_tts', 'openai_tts', 'azure_tts', 'fish_tts'] },
  { key: 'api.base_url', label: 'API Base URL', type: 'text' },
] as const;

function getStatusLabel(status: string | null | undefined) {
  if (!status) {
    return '未开始';
  }
  return STATUS_LABELS[status] ?? status;
}

function getStageLabel(stageId: string) {
  return stageId === 'text' ? 'b. 翻译并生成字幕' : 'c. 配音';
}

function getNestedValue(data: Record<string, unknown>, dottedKey: string): unknown {
  const keys = dottedKey.split('.');
  let current: unknown = data;
  for (const key of keys) {
    if (!current || typeof current !== 'object' || !(key in current)) {
      return undefined;
    }
    current = (current as Record<string, unknown>)[key];
  }
  return current;
}

function isTextPreview(path: string) {
  return ['.srt', '.json', '.txt', '.log', '.md', '.yaml', '.yml'].some((suffix) => path.endsWith(suffix));
}

function isAudioPreview(path: string) {
  return ['.mp3', '.wav', '.m4a', '.flac', '.aac'].some((suffix) => path.endsWith(suffix));
}

function isVideoPreview(path: string) {
  return ['.mp4', '.mov', '.webm', '.mkv'].some((suffix) => path.endsWith(suffix));
}

function getWorkspacePollingInterval(workspace: WorkspaceResponse | undefined) {
  const status = workspace?.project.status;
  return status === 'processing' || status === 'review_required' ? 1000 : false;
}

function ShellLayout() {
  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand">VideoLingo</div>
        <nav className="topnav">
          <NavLink to="/" end>项目总览</NavLink>
          <NavLink to="/settings">全局配置</NavLink>
        </nav>
      </header>
      <main className="canvas">
        <Outlet />
      </main>
    </div>
  );
}

function ProjectsPage() {
  const [searchText, setSearchText] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const { data = [], isLoading } = useQuery({ queryKey: ['projects'], queryFn: api.listProjects });

  const filteredProjects = useMemo(() => {
    return data.filter((project) => {
      const keyword = searchText.toLowerCase();
      const matchesSearch =
        project.name.toLowerCase().includes(keyword)
        || project.source_lang.toLowerCase().includes(keyword)
        || project.target_lang.toLowerCase().includes(keyword);
      const matchesStatus = statusFilter === 'all' ? true : project.status === statusFilter;
      return matchesSearch && matchesStatus;
    });
  }, [data, searchText, statusFilter]);

  return (
    <section className="page">
      <div className="page-header">
        <div>
          <h1>项目总览</h1>
          <p>集中查看所有项目进度、状态与人工审阅阻塞点。</p>
        </div>
        <Link className="primary-button" to="/projects/new">新建项目</Link>
      </div>

      <section className="panel toolbar-panel">
        <label className="toolbar-field">
          搜索项目
          <input value={searchText} onChange={(event) => setSearchText(event.target.value)} placeholder="按项目名或语言搜索" />
        </label>
        <label className="toolbar-field compact-field">
          状态筛选
          <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
            <option value="all">全部状态</option>
            <option value="processing">处理中</option>
            <option value="review_required">待字幕审阅</option>
            <option value="failed">失败</option>
            <option value="completed">已完成</option>
            <option value="archived">已归档</option>
          </select>
        </label>
      </section>

      <div className="panel">
        {isLoading ? <div className="empty-state">正在加载项目...</div> : null}
        {!isLoading && filteredProjects.length === 0 ? <div className="empty-state">没有匹配的项目，先创建一个新的处理任务。</div> : null}
        {filteredProjects.length > 0 ? (
          <div className="project-list">
            {filteredProjects.map((project) => (
              <article className="project-card" key={project.id}>
                <Link className="project-cover clickable-cover" to={`/projects/${project.id}/overview`}>视频</Link>
                <div className="project-body">
                  <div className="project-title-row">
                    <Link className="project-title-link" to={`/projects/${project.id}/overview`}>
                      <h2>{project.name}</h2>
                    </Link>
                    <span className={`status-tag status-${project.status}`}>{getStatusLabel(project.status)}</span>
                  </div>
                  <p>{project.source_lang} → {project.target_lang}</p>
                  <div className="progress-row">
                    <div className="progress-track"><div className="progress-fill" style={{ width: `${project.progress_pct}%` }} /></div>
                    <span>{project.progress_pct}%</span>
                  </div>
                </div>
              </article>
            ))}
          </div>
        ) : null}
      </div>
    </section>
  );
}

function CreateProjectPage() {
  const navigate = useNavigate();
  const queryClientRef = useQueryClient();
  const [name, setName] = useState('');
  const [sourceUriOrPath, setSourceUriOrPath] = useState('');
  const [sourceLang, setSourceLang] = useState('auto');
  const [targetLang, setTargetLang] = useState('zh-CN');
  const [showAdvanced, setShowAdvanced] = useState(false);

  const createMutation = useMutation({
    mutationFn: api.createProject,
    onSuccess: async (project) => {
      await queryClientRef.invalidateQueries({ queryKey: ['projects'] });
      navigate(`/projects/${project.id}/overview`);
    },
  });

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    createMutation.mutate({
      name,
      source_type: sourceUriOrPath.startsWith('http') ? 'remote_url' : 'upload',
      source_uri_or_path: sourceUriOrPath,
      source_lang: sourceLang,
      target_lang: targetLang,
    });
  };

  return (
    <section className="page narrow-page">
      <div className="page-header">
        <div>
          <h1>新建翻译项目</h1>
          <p>上传视频或粘贴链接，创建新的本地化处理任务。</p>
        </div>
      </div>
      {createMutation.error instanceof Error ? (
        <div className="panel" data-testid="create-project-error">{createMutation.error.message}</div>
      ) : null}
      <form className="form-panel" onSubmit={handleSubmit}>
        <label>
          项目名称
          <input data-testid="create-project-name" value={name} onChange={(event) => setName(event.target.value)} placeholder="输入项目名称" required />
        </label>
        <label>
          视频路径或链接
          <input data-testid="create-project-source" value={sourceUriOrPath} onChange={(event) => setSourceUriOrPath(event.target.value)} placeholder="本地路径或 YouTube / Bilibili 链接" required />
        </label>
        <div className="grid-two">
          <label>
            源语言
            <select value={sourceLang} onChange={(event) => setSourceLang(event.target.value)}>
              <option value="auto">自动检测</option>
              <option value="en">英语</option>
              <option value="zh">中文</option>
              <option value="ja">日语</option>
            </select>
          </label>
          <label>
            目标语言
            <select value={targetLang} onChange={(event) => setTargetLang(event.target.value)}>
              <option value="zh-CN">简体中文</option>
              <option value="en">英语</option>
              <option value="ja">日语</option>
            </select>
          </label>
        </div>
        <div className="advanced-block">
          <button className="ghost-button" onClick={() => setShowAdvanced((current) => !current)} type="button">
            {showAdvanced ? '收起高级设置' : '展开高级设置'}
          </button>
          {showAdvanced ? <div className="muted-copy">第一阶段仅保留核心创建参数，其余配置在项目工作区内查看摘要并单独编辑。</div> : null}
        </div>
        <div className="form-actions">
          <Link className="text-link" to="/">取消</Link>
          <button className="primary-button" data-testid="create-project-submit" disabled={createMutation.isPending} type="submit">立即开始</button>
        </div>
      </form>
    </section>
  );
}

function WorkspaceLayout() {
  const { projectId = '' } = useParams();
  const { data, isLoading } = useQuery({
    queryKey: ['workspace', projectId],
    queryFn: () => api.getWorkspace(projectId),
    refetchInterval: (query) => getWorkspacePollingInterval(query.state.data as WorkspaceResponse | undefined),
  });

  if (isLoading) {
    return <section className="page"><div className="empty-state">正在加载项目工作区...</div></section>;
  }

  if (!data) {
    return <section className="page"><div className="empty-state">项目不存在。</div></section>;
  }

  return (
    <section className="workspace-page">
      <aside className="workspace-sidebar">
        <div className="workspace-sidebar-header">
          <h1>{data.project.name}</h1>
          <p>{data.project.source_lang} → {data.project.target_lang}</p>
        </div>
        <nav className="workspace-nav">
          <NavLink to={`/projects/${projectId}/overview`}>概览</NavLink>
          <NavLink to={`/projects/${projectId}/workflow`}>流程</NavLink>
          <NavLink to={`/projects/${projectId}/subtitle-review`}>字幕审阅</NavLink>
          <NavLink to={`/projects/${projectId}/logs-assets`}>日志与产物</NavLink>
        </nav>
        <div className="workspace-meta">
          <span className={`status-tag status-${data.project.status}`} data-testid="workspace-project-status">{getStatusLabel(data.project.status)}</span>
          <div className="progress-row compact-progress">
            <div className="progress-track"><div className="progress-fill" style={{ width: `${data.project.progress_pct}%` }} /></div>
            <span>{data.project.progress_pct}%</span>
          </div>
        </div>
      </aside>
      <div className="workspace-content">
        <Outlet />
      </div>
    </section>
  );
}

function OverviewPage() {
  const { projectId = '' } = useParams();
  const queryClientRef = useQueryClient();
  const { data } = useQuery({
    queryKey: ['workspace', projectId],
    queryFn: () => api.getWorkspace(projectId),
    refetchInterval: (query) => getWorkspacePollingInterval(query.state.data as WorkspaceResponse | undefined),
  });
  const startRunMutation = useMutation({
    mutationFn: () => api.startRun(projectId),
    onSuccess: async () => {
      await Promise.all([
        queryClientRef.invalidateQueries({ queryKey: ['workspace', projectId] }),
        queryClientRef.invalidateQueries({ queryKey: ['projects'] }),
      ]);
    },
  });

  if (!data) return null;

  return (
    <section className="page-section">
      <div className="card-grid">
        <article className="info-card"><span>当前状态</span><strong data-testid="overview-project-status">{getStatusLabel(data.project.status)}</strong></article>
        <article className="info-card"><span>当前阶段</span><strong>{data.project.current_stage ?? '未开始'}</strong></article>
        <article className="info-card"><span>当前步骤</span><strong>{data.project.current_step ?? '未开始'}</strong></article>
      </div>
      <section className="panel">
        <div className="panel-header">
          <h2>关键配置摘要</h2>
          <button className="primary-button small-button" data-testid="overview-start-run" disabled={startRunMutation.isPending || !!data.latest_run_id} onClick={() => startRunMutation.mutate()} type="button">
            {data.latest_run_id ? '已有运行记录' : '启动项目运行'}
          </button>
        </div>
        {startRunMutation.error instanceof Error ? (
          <div className="empty-state" data-testid="overview-start-run-error">{startRunMutation.error.message}</div>
        ) : null}
        <div className="settings-list">
          {Object.entries(data.effective_settings).map(([key, item]) => (
            <div className="settings-row" key={key}>
              <span>{key}</span>
              <div>
                <strong>{String(item.value)}</strong>
                <small>
                  {item.source === 'project_override' ? '项目覆盖' : item.source === 'global_override' ? '全局覆盖' : '配置文件默认值'}
                </small>
              </div>
            </div>
          ))}
        </div>
      </section>
    </section>
  );
}

function WorkflowPage() {
  const { projectId = '' } = useParams();
  const queryClientRef = useQueryClient();
  const { data } = useQuery({
    queryKey: ['workspace', projectId],
    queryFn: () => api.getWorkspace(projectId),
    refetchInterval: (query) => getWorkspacePollingInterval(query.state.data as WorkspaceResponse | undefined),
  });
  const runId = data?.latest_run_id;
  const shouldPoll = getWorkspacePollingInterval(data);
  const { data: nodesResponse } = useQuery({
    queryKey: ['run-nodes', runId],
    queryFn: () => api.getRunNodes(runId!),
    enabled: Boolean(runId),
    refetchInterval: shouldPoll,
  });
  const { data: artifactsResponse } = useQuery({
    queryKey: ['run-artifacts', runId],
    queryFn: () => api.getRunArtifacts(runId!),
    enabled: Boolean(runId),
    refetchInterval: shouldPoll,
  });
  const actionMutation = useMutation({
    mutationFn: ({ action, stepId }: { action: string; stepId: string }) => api.runAction(runId!, { action, step_id: stepId }),
    onSuccess: async () => {
      await Promise.all([
        queryClientRef.invalidateQueries({ queryKey: ['workspace', projectId] }),
        queryClientRef.invalidateQueries({ queryKey: ['projects'] }),
        queryClientRef.invalidateQueries({ queryKey: ['run-nodes', runId] }),
        queryClientRef.invalidateQueries({ queryKey: ['run-artifacts', runId] }),
        queryClientRef.invalidateQueries({ queryKey: ['run-logs', runId] }),
      ]);
    },
  });

  const nodeMap = useMemo(() => new Map((nodesResponse?.nodes ?? []).map((node) => [node.step_id, node])), [nodesResponse]);
  const artifactMap = useMemo(() => new Map((artifactsResponse?.artifacts ?? []).map((group) => [group.step_id, group.files])), [artifactsResponse]);

  if (!data) return null;

  return (
    <section className="page-section">
      {!runId ? <section className="panel"><div className="empty-state">当前项目还没有运行记录，先在概览页启动一次运行。</div></section> : null}
      {data.stages.map((stage) => (
        <section className="panel" key={stage.stage_id}>
          <div className="panel-header">
            <h2>{getStageLabel(stage.stage_id)}</h2>
          </div>
          <div className="workflow-grid">
            {stage.steps.map((step) => {
              const node = nodeMap.get(step.step_id);
              const files = artifactMap.get(step.step_id) ?? [];
              const isActive = step.step_id === data.project.current_step;
              return (
                <article className={`workflow-node ${isActive ? 'active' : ''}`} data-testid={`workflow-node-${step.step_id}`} key={step.step_id}>
                  <div className="node-header">
                    <span className="node-id">{step.step_id}</span>
                    <span className={`status-tag status-${node?.status ?? 'pending'}`} data-testid={`workflow-node-status-${step.step_id}`}>{getStatusLabel(node?.status)}</span>
                  </div>
                  <h3>{step.title}</h3>
                  <p>依赖：{step.depends_on.length > 0 ? step.depends_on.join('、') : '无'}</p>
                  <p>产物：{files.length > 0 ? `${files.length} 个文件` : '暂无'}</p>
                  {runId ? (
                    <div className="stack-actions">
                      <button
                        className="ghost-button"
                        data-testid={`workflow-action-run_step-${step.step_id}`}
                        disabled={actionMutation.isPending}
                        onClick={() => actionMutation.mutate({ action: 'run_step', stepId: step.step_id })}
                        type="button"
                      >
                        仅运行本步
                      </button>
                      <button
                        className="ghost-button"
                        data-testid={`workflow-action-rerun_step-${step.step_id}`}
                        disabled={actionMutation.isPending}
                        onClick={() => actionMutation.mutate({ action: 'rerun_step', stepId: step.step_id })}
                        type="button"
                      >
                        重跑本步
                      </button>
                      <button
                        className="ghost-button"
                        data-testid={`workflow-action-rerun_from_step-${step.step_id}`}
                        disabled={actionMutation.isPending}
                        onClick={() => actionMutation.mutate({ action: 'rerun_from_step', stepId: step.step_id })}
                        type="button"
                      >
                        从本步重跑到结束
                      </button>
                      <button
                        className="ghost-button"
                        data-testid={`workflow-action-cleanup_step_and_downstream-${step.step_id}`}
                        disabled={actionMutation.isPending}
                        onClick={() => actionMutation.mutate({ action: 'cleanup_step_and_downstream', stepId: step.step_id })}
                        type="button"
                      >
                        清理本步及下游
                      </button>
                    </div>
                  ) : null}
                  <details>
                    <summary>查看详情</summary>
                    <div className="node-details">
                      <div>
                        <strong>输入依赖</strong>
                        <div>{step.depends_on.length > 0 ? step.depends_on.join('、') : '无'}</div>
                      </div>
                      <div>
                        <strong>输出产物</strong>
                        <ul>
                          {files.length > 0 ? files.map((artifact) => <li key={artifact}>{artifact}</li>) : <li>暂无产物</li>}
                        </ul>
                      </div>
                      <div>
                        <strong>日志摘录</strong>
                        <div>{node?.log_excerpt ?? '暂无日志摘录'}</div>
                      </div>
                      <div>
                        <strong>失败摘要</strong>
                        <div>{node?.error_summary ?? '暂无失败信息'}</div>
                      </div>
                    </div>
                  </details>
                </article>
              );
            })}
          </div>
        </section>
      ))}
    </section>
  );
}

function SubtitleReviewPage() {
  const { projectId = '' } = useParams();
  const queryClientRef = useQueryClient();
  const [searchText, setSearchText] = useState('');
  const [draftRows, setDraftRows] = useState<SubtitleReviewRow[]>([]);
  const { data: workspace } = useQuery({
    queryKey: ['workspace', projectId],
    queryFn: () => api.getWorkspace(projectId),
    refetchInterval: (query) => getWorkspacePollingInterval(query.state.data as WorkspaceResponse | undefined),
  });
  const reviewPollingInterval = getWorkspacePollingInterval(workspace);
  const { data } = useQuery({
    queryKey: ['subtitle-review', projectId],
    queryFn: () => api.getSubtitleReview(projectId),
    refetchInterval: reviewPollingInterval,
  });

  useEffect(() => {
    setDraftRows(data?.rows ?? []);
  }, [data]);

  const filteredRows = draftRows.filter((row) => row.source_text.includes(searchText) || row.target_text.includes(searchText));

  const saveMutation = useMutation({
    mutationFn: (payload: { rows: SubtitleReviewRow[] }) => api.saveSubtitleReview(projectId, payload),
    onSuccess: async () => {
      await queryClientRef.invalidateQueries({ queryKey: ['subtitle-review', projectId] });
    },
  });

  const approveMutation = useMutation({
    mutationFn: async () => {
      const runId = workspace?.latest_run_id;
      if (!runId) {
        throw new Error('当前项目没有运行记录，无法继续。');
      }
      await api.runAction(runId, { action: 'approve_subtitles_and_continue' });
    },
    onSuccess: async () => {
      await Promise.all([
        queryClientRef.invalidateQueries({ queryKey: ['workspace', projectId] }),
        queryClientRef.invalidateQueries({ queryKey: ['projects'] }),
      ]);
    },
  });

  const updateRow = (rowId: string, targetText: string) => {
    setDraftRows((currentRows) => currentRows.map((row) => (row.row_id === rowId ? { ...row, target_text: targetText } : row)));
  };

  return (
    <section className="page-section">
      <section className="review-layout">
        <div className="panel review-video-panel">
          <h2>视频预览</h2>
          <div className="video-placeholder">第一阶段保留预览位，后续接入真实视频源</div>
          <label>
            全局查找
            <input value={searchText} onChange={(event) => setSearchText(event.target.value)} placeholder="搜索原文或译文" />
          </label>
          <div className="stack-actions">
            <button className="primary-button small-button" data-testid="subtitle-review-save" onClick={() => saveMutation.mutate({ rows: draftRows })} type="button">保存修改</button>
            <button className="ghost-button" data-testid="subtitle-review-approve" onClick={() => approveMutation.mutate()} type="button">审阅通过并继续</button>
          </div>
        </div>
        <div className="panel review-table-panel">
          <div className="panel-header">
            <h2>双语字幕</h2>
            <span className="muted-copy">以结构化字幕为主，SRT 只作为预览结果。</span>
          </div>
          <div className="review-table">
            <div className="review-table-header"><span>时间</span><span>原文</span><span>译文</span></div>
            {filteredRows.length === 0 ? <div className="empty-state">暂无字幕数据。</div> : null}
            {filteredRows.map((row) => (
              <div className="review-row" data-testid={`subtitle-review-row-${row.row_id}`} key={row.row_id}>
                <span>{row.start} - {row.end}</span>
                <span>{row.source_text}</span>
                <textarea data-testid={`subtitle-review-target-${row.row_id}`} value={row.target_text} onChange={(event) => updateRow(row.row_id, event.target.value)} />
              </div>
            ))}
          </div>
        </div>
      </section>
    </section>
  );
}

function ArtifactPreview({ path }: { path: string | null }) {
  const shouldLoadText = Boolean(path) && isTextPreview(path!);
  const { data } = useQuery({
    queryKey: ['artifact-text', path],
    queryFn: async () => {
      const response = await fetch(api.getArtifactUrl(path!));
      return response.text();
    },
    enabled: shouldLoadText,
  });

  if (!path) {
    return <div className="empty-state">选择左侧文件后在这里预览。</div>;
  }

  if (isTextPreview(path)) {
    return <pre className="preview-console">{data ?? '正在加载文本预览...'}</pre>;
  }

  if (isAudioPreview(path)) {
    return <audio className="media-preview" controls src={api.getArtifactUrl(path)} />;
  }

  if (isVideoPreview(path)) {
    return <video className="media-preview" controls src={api.getArtifactUrl(path)} />;
  }

  return <div className="empty-state">当前文件类型暂不支持预览，可通过接口直接下载查看。</div>;
}

function LogsAssetsPage() {
  const { projectId = '' } = useParams();
  const { data: workspace } = useQuery({
    queryKey: ['workspace', projectId],
    queryFn: () => api.getWorkspace(projectId),
    refetchInterval: (query) => getWorkspacePollingInterval(query.state.data as WorkspaceResponse | undefined),
  });
  const runId = workspace?.latest_run_id;
  const refetchInterval = getWorkspacePollingInterval(workspace);
  const { data: logsResponse } = useQuery({
    queryKey: ['run-logs', runId],
    queryFn: () => api.getRunLogs(runId!),
    enabled: Boolean(runId),
    refetchInterval,
  });
  const { data: artifactsResponse } = useQuery({
    queryKey: ['run-artifacts', runId],
    queryFn: () => api.getRunArtifacts(runId!),
    enabled: Boolean(runId),
    refetchInterval,
  });
  const [selectedArtifact, setSelectedArtifact] = useState<string | null>(null);

  useEffect(() => {
    const firstFile = artifactsResponse?.artifacts.find((group) => group.files.length > 0)?.files[0] ?? null;
    setSelectedArtifact(firstFile);
  }, [artifactsResponse]);

  return (
    <section className="page-section two-column-grid">
      <section className="panel">
        <h2>运行日志</h2>
        {!runId ? <div className="empty-state">当前项目没有运行记录。</div> : null}
        {(logsResponse?.logs ?? []).length === 0 && runId ? <div className="empty-state">暂时没有日志文件。</div> : null}
        {(logsResponse?.logs ?? []).map((entry) => (
          <details className="log-entry" key={entry.name} open={logsResponse?.logs.length === 1}>
            <summary>{entry.name}</summary>
            <pre className="log-console">{entry.content}</pre>
          </details>
        ))}
      </section>
      <section className="panel artifact-panel">
        <h2>节点产物</h2>
        {!runId ? <div className="empty-state">当前项目没有运行记录。</div> : null}
        <div className="artifact-layout">
          <div className="artifact-list">
            {(artifactsResponse?.artifacts ?? []).map((group) => (
              <div className="artifact-group" key={group.step_id}>
                <strong>{group.step_id}</strong>
                {group.files.length === 0 ? <div className="muted-copy">暂无产物</div> : null}
                {group.files.map((file) => (
                  <button className={`artifact-link ${selectedArtifact === file ? 'active' : ''}`} key={file} onClick={() => setSelectedArtifact(file)} type="button">
                    {file}
                  </button>
                ))}
              </div>
            ))}
          </div>
          <div className="artifact-preview">
            <ArtifactPreview path={selectedArtifact} />
          </div>
        </div>
      </section>
    </section>
  );
}

function SettingsPage() {
  const queryClientRef = useQueryClient();
  const { data, isLoading } = useQuery({ queryKey: ['settings'], queryFn: api.getSettings });
  const [formState, setFormState] = useState<Record<string, string>>({});

  useEffect(() => {
    if (!data?.global) {
      return;
    }
    const nextState: Record<string, string> = {};
    for (const field of SETTING_FIELDS) {
      const value = getNestedValue(data.global, field.key);
      nextState[field.key] = typeof value === 'boolean' ? String(value) : String(value ?? '');
    }
    setFormState(nextState);
  }, [data]);

  const saveMutation = useMutation({
    mutationFn: () => api.updateSettings({
      overrides: {
        target_language: formState.target_language,
        'whisper.runtime': formState['whisper.runtime'],
        demucs: formState.demucs === 'true',
        tts_method: formState.tts_method,
        'api.base_url': formState['api.base_url'],
      },
    }),
    onSuccess: async () => {
      await queryClientRef.invalidateQueries({ queryKey: ['settings'] });
    },
  });

  if (isLoading) return <section className="page"><div className="empty-state">正在加载全局配置...</div></section>;

  return (
    <section className="page">
      <div className="page-header">
        <div>
          <h1>全局配置</h1>
          <p>管理默认配置。敏感字段统一掩码显示，不在页面和日志中明文回显。</p>
        </div>
      </div>
      <section className="panel settings-editor-panel">
        <div className="settings-form-grid">
          {SETTING_FIELDS.map((field) => (
            <label key={field.key}>
              {field.label}
              {field.type === 'select' ? (
                <select value={formState[field.key] ?? ''} onChange={(event) => setFormState((current) => ({ ...current, [field.key]: event.target.value }))}>
                  {field.options?.map((option) => <option key={option} value={option}>{option}</option>)}
                </select>
              ) : field.type === 'boolean' ? (
                <select value={formState[field.key] ?? 'false'} onChange={(event) => setFormState((current) => ({ ...current, [field.key]: event.target.value }))}>
                  <option value="true">true</option>
                  <option value="false">false</option>
                </select>
              ) : (
                <input value={formState[field.key] ?? ''} onChange={(event) => setFormState((current) => ({ ...current, [field.key]: event.target.value }))} />
              )}
            </label>
          ))}
        </div>
        <div className="panel-actions">
          <button className="primary-button small-button" disabled={saveMutation.isPending} onClick={() => saveMutation.mutate()} type="button">保存全局覆盖</button>
        </div>
      </section>
      <section className="panel settings-tree">
        <h2>当前生效的全局配置</h2>
        <pre>{JSON.stringify(data?.global ?? {}, null, 2)}</pre>
      </section>
    </section>
  );
}

export function AppRouter() {
  return (
    <QueryClientProvider client={queryClient}>
      <Routes>
        <Route element={<ShellLayout />} path="/">
          <Route element={<ProjectsPage />} index />
          <Route element={<CreateProjectPage />} path="projects/new" />
          <Route element={<WorkspaceLayout />} path="projects/:projectId">
            <Route element={<OverviewPage />} path="overview" />
            <Route element={<WorkflowPage />} path="workflow" />
            <Route element={<SubtitleReviewPage />} path="subtitle-review" />
            <Route element={<LogsAssetsPage />} path="logs-assets" />
          </Route>
          <Route element={<SettingsPage />} path="settings" />
        </Route>
      </Routes>
    </QueryClientProvider>
  );
}
