import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest';

import { AppRouter } from '../app/router';

describe('AppRouter', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      json: async () => [],
      text: async () => '',
    })));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  test('renders project list page on root route', async () => {
    render(
      <MemoryRouter initialEntries={['/']}>
        <AppRouter />
      </MemoryRouter>,
    );

    expect(await screen.findByRole('heading', { name: '项目总览' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '新建项目' })).toBeInTheDocument();
  });

  test('renders create project page', async () => {
    render(
      <MemoryRouter initialEntries={['/projects/new']}>
        <AppRouter />
      </MemoryRouter>,
    );

    expect(await screen.findByRole('heading', { name: '新建翻译项目' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '立即开始' })).toBeInTheDocument();
  });
});
