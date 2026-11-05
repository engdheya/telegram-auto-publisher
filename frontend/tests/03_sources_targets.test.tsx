import { describe, expect, it } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { SourcesPage } from '../src/pages/SourcesPage';
import { TargetsPage } from '../src/pages/TargetsPage';
import { mockFetch, renderWithProviders, mockSource, mockTarget, callsTo, lastBody } from './helpers';

describe('Sources page (wired to real endpoints)', () => {
  it('lists sources with baseline/last processed ids and monitoring status', async () => {
    mockFetch({ '/sources': () => [mockSource] });

    renderWithProviders(<SourcesPage />);

    expect(await screen.findByTestId('sources-page')).toBeInTheDocument();
    expect(screen.getByText('Source A')).toBeInTheDocument();
    expect(screen.getByText('@source_a')).toBeInTheDocument();
    expect(screen.getByText('ACTIVE')).toBeInTheDocument();
    expect(screen.getByText('500 / 512')).toBeInTheDocument();
  });

  it('creates a source through POST /api/v1/sources with the trimmed payload', async () => {
    const fetchMock = mockFetch({
      '/sources': (url, init) => (init?.method === 'POST' ? mockSource : [mockSource]),
    });

    renderWithProviders(<SourcesPage />);
    await screen.findByTestId('sources-page');

    await userEvent.click(screen.getByRole('button', { name: /إضافة مصدر/ }));
    const dialog = await screen.findByRole('dialog');
    const inputs = within(dialog).getAllByRole('textbox');
    await userEvent.type(inputs[0], 'Source B');
    await userEvent.type(inputs[1], '@source_b');
    await userEvent.click(within(dialog).getByRole('button', { name: 'حفظ' }));

    await waitFor(() => {
      expect(callsTo(fetchMock, '/api/v1/sources').filter(([, i]) => i?.method === 'POST').length).toBe(1);
    });
    expect(lastBody(fetchMock, '/api/v1/sources')).toMatchObject({
      title: 'Source B',
      identifier: '@source_b',
      is_enabled: true,
    });
  });

  it('calls the verify and start-monitoring endpoints', async () => {
    const fetchMock = mockFetch({
      '/sources/11/verify': () => ({ accessible: true, source: mockSource, detail: 'Access verified.' }),
      '/sources/11/stop': () => ({ ...mockSource, monitoring_status: 'PAUSED' }),
      '/sources/11/start': () => mockSource,
      '/sources': () => [{ ...mockSource, monitoring_status: 'PAUSED' }],
    });

    renderWithProviders(<SourcesPage />);
    await screen.findByTestId('sources-page');

    await userEvent.click(await screen.findByRole('button', { name: /اختبار الوصول/ }));
    await waitFor(() => expect(callsTo(fetchMock, '/api/v1/sources/11/verify').length).toBe(1));
    expect(callsTo(fetchMock, '/api/v1/sources/11/verify')[0][1]?.method).toBe('POST');

    await userEvent.click(await screen.findByRole('button', { name: /بدأ المراقبة/ }));
    await waitFor(() => expect(callsTo(fetchMock, '/api/v1/sources/11/start').length).toBe(1));
  });
});

describe('Targets page (permission verification + real test post)', () => {
  it('shows permission badges and verifies permissions through the API', async () => {
    const fetchMock = mockFetch({
      '/targets/21/verify': () => ({ ok: true, target: mockTarget, detail: 'Permissions verified.' }),
      '/targets': () => [mockTarget],
    });

    renderWithProviders(<TargetsPage />);
    expect(await screen.findByTestId('targets-page')).toBeInTheDocument();
    expect(screen.getByText('VERIFIED')).toBeInTheDocument();
    expect(screen.getByText('post')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: /^تحقق$/ }));
    await waitFor(() => expect(callsTo(fetchMock, '/api/v1/targets/21/verify').length).toBe(1));
  });

  it('sends a real test post and renders backend failure reasons', async () => {
    const fetchMock = mockFetch({
      '/targets/21/test-publish': () => ({
        ok: false,
        target: { ...mockTarget, can_post_messages: false },
        detail: 'ChatWriteForbiddenError: not enough rights to send text messages',
        test_message_id: null,
      }),
      '/targets': () => [mockTarget],
    });

    renderWithProviders(<TargetsPage />);
    await screen.findByTestId('targets-page');

    await userEvent.click(screen.getByRole('button', { name: /اختبار النشر/ }));
    const dialog = await screen.findByRole('dialog');
    await userEvent.click(within(dialog).getByRole('button', { name: /إرسال المنشور التجريبي/ }));

    expect((await screen.findAllByText(/not enough rights to send text messages/)).length).toBeGreaterThan(0);
    expect(lastBody(fetchMock, '/api/v1/targets/21/test-publish')).toHaveProperty('message');
  });
});
