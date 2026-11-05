import { describe, expect, it } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { RoutesPage } from '../src/pages/RoutesPage';
import {
  callsTo,
  lastBody,
  mockFetch,
  mockRoute,
  mockSource,
  mockTarget,
  renderWithProviders,
} from './helpers';

const listHandlers = () => ({
  '/routes': (url: string, init?: RequestInit) => {
    if (init?.method === 'POST') return init?.body && String(init.body).includes('source_channel_ids') ? [mockRoute] : mockRoute;
    return [mockRoute];
  },
  '/sources': () => [mockSource, { ...mockSource, id: 12, title: 'Source B', identifier: '@source_b' }],
  '/targets': () => [mockTarget, { ...mockTarget, id: 22, title: 'Target 2', identifier: '@target_2' }],
});

describe('Routes page — independent 1→1 / 1→N / N→1 / N→N routing', () => {
  it('renders each route with its source → target mapping and filter summary', async () => {
    mockFetch(listHandlers());
    renderWithProviders(<RoutesPage />);

    expect(await screen.findByTestId('routes-page')).toBeInTheDocument();
    expect(screen.getByText('Source A → Target 1')).toBeInTheDocument();
    expect(screen.getByText('Source A')).toBeInTheDocument();
    expect(screen.getByText('Target 1')).toBeInTheDocument();
    const chips = screen.getByTestId('route-chips-31');
    expect(within(chips).getByText(/توقيع/)).toHaveTextContent('@target_1');
    expect(within(chips).getByText('نشط')).toBeInTheDocument();
  });

  it('toggles a single route through POST /routes/{id}/toggle without touching others', async () => {
    const fetchMock = mockFetch({
      ...listHandlers(),
      '/routes/31/toggle': () => ({ ...mockRoute, is_enabled: false }),
    });

    renderWithProviders(<RoutesPage />);
    await screen.findByTestId('routes-page');

    const toggle = screen.getByRole('switch', { name: undefined });
    await userEvent.click(toggle);

    await waitFor(() => expect(callsTo(fetchMock, '/api/v1/routes/31/toggle').length).toBe(1));
    expect(callsTo(fetchMock, '/api/v1/routes/31/toggle')[0][1]?.method).toBe('POST');
  });

  it('creates N×M routes atomically through POST /routes/bulk', async () => {
    const fetchMock = mockFetch({
      ...listHandlers(),
      '/routes/bulk': () => [mockRoute, { ...mockRoute, id: 32 }, { ...mockRoute, id: 33, target_channel_id: 22 }],
    });

    renderWithProviders(<RoutesPage />);
    await screen.findByTestId('routes-page');

    await userEvent.click(screen.getByRole('button', { name: /إنشاء مسار/ }));
    const dialog = await screen.findByRole('dialog');

    await userEvent.click(within(dialog).getByRole('button', { name: /ربط متعدد/ }));
    await userEvent.click(within(dialog).getByRole('checkbox', { name: /Source A/ }));
    await userEvent.click(within(dialog).getByRole('checkbox', { name: /Source B/ }));
    await userEvent.click(within(dialog).getByRole('checkbox', { name: /Target 1/ }));
    await userEvent.click(within(dialog).getByRole('checkbox', { name: /Target 2/ }));

    expect(within(dialog).getByText(/سيتم إنشاء/)).toHaveTextContent('4');

    await userEvent.click(within(dialog).getByRole('button', { name: /إنشاء 4 مسار/ }));

    await waitFor(() => expect(callsTo(fetchMock, '/api/v1/routes/bulk').length).toBe(1));
    expect(lastBody(fetchMock, '/api/v1/routes/bulk')).toMatchObject({
      source_channel_ids: [11, 12],
      target_channel_ids: [21, 22],
      is_enabled: true,
    });
  });

  it('persists the full route_filters payload from the filters modal', async () => {
    const fetchMock = mockFetch({
      ...listHandlers(),
    });

    renderWithProviders(<RoutesPage />);
    await screen.findByTestId('routes-page');

    await userEvent.click(screen.getByRole('button', { name: /القواعد/ }));
    const dialog = await screen.findByRole('dialog');

    // toggle a content type off (photo)
    await userEvent.click(within(dialog).getByRole('button', { name: 'صورة' }));
    await userEvent.type(within(dialog).getByLabelText(/كلمات يجب توفرها/), 'breaking,urgent');
    await userEvent.type(within(dialog).getByLabelText(/أدنى طول نص/), '20');
    await userEvent.type(within(dialog).getByLabelText(/امتدادات الملفات المسموحة/), '.pdf, .mp4');
    await userEvent.type(within(dialog).getByLabelText(/نص يُضاف قبل المنشور/), '📌 ');
    await userEvent.click(within(dialog).getByRole('button', { name: /حفظ القواعد/ }));

    await waitFor(() =>
      expect(callsTo(fetchMock, '/api/v1/routes/31').filter(([, i]) => i?.method === 'PATCH').length).toBe(1)
    );

    const body = lastBody(fetchMock, '/api/v1/routes/31');
    expect(body.filters.allowed_content_types).not.toContain('photo');
    expect(body.filters.allowed_content_types).toContain('text');
    expect(body.filters.include_keywords).toEqual(['breaking', 'urgent']);
    expect(body.filters.allowed_extensions).toEqual(['.pdf', '.mp4']);
    expect(body.filters.min_text_length).toBe(20);
    expect(body.filters.prefix_text).toBe('📌 ');
  });

  it('deletes a route only after confirmation', async () => {
    const fetchMock = mockFetch({
      ...listHandlers(),
      '/routes/31': (_url, init) => (init?.method === 'DELETE' ? {} : mockRoute),
    });

    renderWithProviders(<RoutesPage />);
    await screen.findByTestId('routes-page');

    await userEvent.click(screen.getByRole('button', { name: /^حذف$/ }));
    const dialog = await screen.findByRole('dialog');
    expect(callsTo(fetchMock, '/api/v1/routes/31').filter(([, i]) => i?.method === 'DELETE').length).toBe(0);

    await userEvent.click(within(dialog).getByRole('button', { name: 'حذف' }));
    await waitFor(() =>
      expect(callsTo(fetchMock, '/api/v1/routes/31').filter(([, i]) => i?.method === 'DELETE').length).toBe(1)
    );
  });
});
