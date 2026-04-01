import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest';

import { AppRouter } from '../app/router';
import { queryClient } from '../app/query-client';

const workspaceResponse = {
  project: {
    id: '1',
    name: '示例项目',
    source_type: 'remote_video',
    source_uri_or_path: 'https://example.com/video',
    source_lang: 'en',
    target_lang: 'zh',
    status: 'review_required',
    progress_pct: 50,
    current_stage: 'text',
    current_step: 'b5_generate_subtitles',
    cover_path: null,
    created_at: '2026-04-01T00:00:00Z',
    updated_at: '2026-04-01T00:00:00Z',
  },
  stages: [
    {
      stage_id: 'text',
      steps: [
        {
          step_id: 'b5_generate_subtitles',
          title: '生成字幕',
          depends_on: ['b4'],
          artifact_patterns: ['output/review/*.json'],
          preview_patterns: [],
        },
      ],
    },
  ],
  effective_settings: {},
  latest_run_id: '1',
};

const nodesResponse = {
  run_id: '1',
  nodes: [
    {
      step_id: 'b5_generate_subtitles',
      stage_id: 'text',
      status: 'completed',
      title: '生成字幕',
      artifact_patterns: [],
      depends_on: ['b4'],
      log_excerpt: 'done',
      error_summary: null,
    },
  ],
};

const artifactsResponse = {
  run_id: '1',
  artifacts: [
    {
      step_id: 'b5_generate_subtitles',
      stage_id: 'text',
      files: ['output/review/subtitles.json'],
    },
  ],
};

const subtitleReviewResponse = {
  rows: [
    {
      row_id: 'row-1',
      start: '00:00:00.000',
      end: '00:00:01.000',
      source_text: 'hello',
      target_text: '你好',
    },
  ],
};

function createJsonResponse(payload: unknown) {
  return {
    ok: true,
    json: async () => payload,
    text: async () => JSON.stringify(payload),
  };
}

describe('控制面流程动作', () => {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);

    if (url.endsWith('/projects/1/workspace')) {
      return createJsonResponse(workspaceResponse);
    }

    if (url.endsWith('/runs/1/nodes')) {
      return createJsonResponse(nodesResponse);
    }

    if (url.endsWith('/runs/1/artifacts')) {
      return createJsonResponse(artifactsResponse);
    }

    if (url.endsWith('/runs/1/logs')) {
      return createJsonResponse({ run_id: '1', logs: [] });
    }

    if (url.endsWith('/projects/1/subtitle-review') && (!init?.method || init.method === 'GET')) {
      return createJsonResponse(subtitleReviewResponse);
    }

    if (url.endsWith('/projects/1/subtitle-review') && init?.method === 'PUT') {
      return createJsonResponse(subtitleReviewResponse);
    }

    if (url.endsWith('/runs/1/actions') && init?.method === 'POST') {
      return createJsonResponse({ run_id: '1', accepted: true, action: 'ok' });
    }

    if (url.endsWith('/projects')) {
      return createJsonResponse([]);
    }

    throw new Error(`未处理的请求: ${url}`);
  });

  beforeEach(() => {
    queryClient.clear();
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    queryClient.clear();
    vi.unstubAllGlobals();
    fetchMock.mockClear();
  });

  test('流程页会发送节点动作请求', async () => {
    render(
      <MemoryRouter initialEntries={['/projects/1/workflow']}>
        <AppRouter />
      </MemoryRouter>,
    );

    const rerunButton = await screen.findByTestId('workflow-action-rerun_from_step-b5_generate_subtitles');
    fireEvent.click(rerunButton);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        'http://127.0.0.1:8000/runs/1/actions',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ action: 'rerun_from_step', step_id: 'b5_generate_subtitles' }),
        }),
      );
    });
  });

  test('字幕审阅页支持保存与继续动作', async () => {
    render(
      <MemoryRouter initialEntries={['/projects/1/subtitle-review']}>
        <AppRouter />
      </MemoryRouter>,
    );

    const saveButton = await screen.findByTestId('subtitle-review-save');
    fireEvent.click(saveButton);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        'http://127.0.0.1:8000/projects/1/subtitle-review',
        expect.objectContaining({
          method: 'PUT',
          body: JSON.stringify(subtitleReviewResponse),
        }),
      );
    });

    const approveButton = screen.getByTestId('subtitle-review-approve');
    fireEvent.click(approveButton);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        'http://127.0.0.1:8000/runs/1/actions',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ action: 'approve_subtitles_and_continue' }),
        }),
      );
    });
  });

  test('运行中的工作区会轮询刷新状态', async () => {
    let workspaceCallCount = 0;

    const pollingFetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith('/projects/1/workspace')) {
        workspaceCallCount += 1;
        const status = workspaceCallCount > 1 ? 'review_required' : 'processing';
        return createJsonResponse({
          ...workspaceResponse,
          project: {
            ...workspaceResponse.project,
            status,
          },
        });
      }

      if (url.endsWith('/projects')) {
        return createJsonResponse([]);
      }

      throw new Error(`未处理的请求: ${url}`);
    });

    vi.stubGlobal('fetch', pollingFetchMock);

    render(
      <MemoryRouter initialEntries={['/projects/1/overview']}>
        <AppRouter />
      </MemoryRouter>,
    );

    expect(await screen.findByTestId('workspace-project-status')).toHaveTextContent('处理中');
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 1300));
    });

    await waitFor(() => {
      expect(screen.getByTestId('workspace-project-status')).toHaveTextContent('待字幕审阅');
    });
  });

  test('概览页会展示启动运行失败原因', async () => {
    const failureFetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);

      if (url.endsWith('/projects/1/workspace')) {
        return createJsonResponse({
          ...workspaceResponse,
          project: {
            ...workspaceResponse.project,
            status: 'draft',
          },
          latest_run_id: null,
        });
      }

      if (url.endsWith('/projects')) {
        return createJsonResponse([]);
      }

      if (url.endsWith('/projects/1/runs') && init?.method === 'POST') {
        return {
          ok: false,
          text: async () => JSON.stringify({ detail: 'YouTube 当前要求额外的人机校验，请刷新 cookies 后重试。' }),
        };
      }

      throw new Error(`未处理的请求: ${url}`);
    });

    vi.stubGlobal('fetch', failureFetchMock);

    render(
      <MemoryRouter initialEntries={['/projects/1/overview']}>
        <AppRouter />
      </MemoryRouter>,
    );

    fireEvent.click(await screen.findByTestId('overview-start-run'));

    await waitFor(() => {
      expect(screen.getByTestId('overview-start-run-error')).toHaveTextContent('YouTube 当前要求额外的人机校验');
    });
  });
});
