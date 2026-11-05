import { describe, expect, it } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MessagesPage } from '../src/pages/MessagesPage';
import { QueuePage } from '../src/pages/QueuePage';
import { callsTo, mockFetch, mockJob, mockMessage, renderWithProviders } from './helpers';

const queueResponse = (job = mockJob) => ({
  total: 1,
  page: 1,
  page_size: 25,
  counts_by_status: {
    QUEUED: 0,
    PROCESSING: 0,
    PUBLISHED: 1,
    RETRY_WAIT: 0,
    SKIPPED: 0,
    FAILED: 0,
    UNKNOWN: 0,
  },
  items: [job],
});

describe('Messages / publishing history page', () => {
  it('renders received events with per-target job status and target message id', async () => {
    mockFetch({
      '/messages': () => ({ total: 1, page: 1, page_size: 20, items: [mockMessage] }),
      '/sources': () => [],
    });

    renderWithProviders(<MessagesPage />);
    expect(await screen.findByTestId('messages-page')).toBeInTheDocument();
    expect(screen.getByText(/Hello world/)).toBeInTheDocument();
    expect(screen.getByText('PUBLISHED')).toBeInTheDocument();

    // expand the event row to inspect job details
    await userEvent.click(screen.getByText(/Hello world/));

    expect(await screen.findByText('target msg #900')).toBeInTheDocument();
    expect(screen.getByText(/route_name|Source A → Target 1/)).toBeInTheDocument();
  });

  it('flags protected (noforwards) content and never offers a bypass', async () => {
    mockFetch({
      '/messages': () => ({
        total: 1,
        page: 1,
        page_size: 20,
        items: [
          {
            ...mockMessage,
            is_protected_content: true,
            protection_reason: 'noforwards: content protection enabled by channel owner',
            jobs: [{ ...mockMessage.jobs[0], status: 'SKIPPED', skip_reason: 'PROTECTED_CONTENT: noforwards' }],
          },
        ],
      }),
      '/sources': () => [],
    });

    renderWithProviders(<MessagesPage />);
    await screen.findByTestId('messages-page');

    expect(screen.getByText('محمي')).toBeInTheDocument();
    await userEvent.click(screen.getByText(/Hello world/));
    expect(await screen.findByText(/content protection enabled by channel owner/)).toBeInTheDocument();
    expect(screen.getAllByText('SKIPPED').length).toBeGreaterThan(0);
    // no manual retry offered for protected content
    expect(screen.queryByRole('button', { name: /إعادة محاولة/ })).toBeNull();
  });

  it('retries a failed job through the queue retry endpoint', async () => {
    const failed = { ...mockMessage.jobs[0], status: 'FAILED' as const, last_error: 'FloodWait 30s' };
    const fetchMock = mockFetch({
      '/queue/jobs/101/retry': () => ({ ok: true, detail: 'Job #101 re-queued as QUEUED.', job: { ...mockJob, status: 'QUEUED' } }),
      '/messages': () => ({
        total: 1,
        page: 1,
        page_size: 20,
        items: [{ ...mockMessage, jobs: [failed] }],
      }),
      '/sources': () => [],
    });

    renderWithProviders(<MessagesPage />);
    await screen.findByTestId('messages-page');
    await userEvent.click(screen.getByText(/Hello world/));

    await userEvent.click(await screen.findByRole('button', { name: /إعادة محاولة/ }));
    await waitFor(() => expect(callsTo(fetchMock, '/api/v1/queue/jobs/101/retry').length).toBe(1));
  });
});

describe('Queue management page', () => {
  it('shows status counts and job attempt history', async () => {
    mockFetch({ '/queue/jobs': () => queueResponse() });

    renderWithProviders(<QueuePage />);
    expect(await screen.findByTestId('queue-page')).toBeInTheDocument();
    expect(screen.getByText('PUBLISHED')).toBeInTheDocument();
    expect(screen.getByText('#101')).toBeInTheDocument();

    await userEvent.click(screen.getByText('#101'));
    expect(await screen.findByText('worker-1')).toBeInTheDocument();
    expect(screen.getByText('#1 SUCCESS')).toBeInTheDocument();
  });

  it('reconciles UNKNOWN jobs before retrying (no blind duplicate post)', async () => {
    const unknownJob = { ...mockJob, status: 'UNKNOWN' as const, unknown_reason: 'Worker crashed mid-publish', target_message_id: null };
    const fetchMock = mockFetch({
      '/queue/jobs/101/reconcile': () => ({
        ok: true,
        detail: 'Reconciliation found the post (message #900); job marked PUBLISHED.',
        job: mockJob,
      }),
      '/queue/jobs': () => queueResponse(unknownJob),
    });

    renderWithProviders(<QueuePage />);
    await screen.findByTestId('queue-page');
    expect(screen.getAllByText('UNKNOWN').length).toBeGreaterThan(0);

    await userEvent.click(screen.getByRole('button', { name: /مصالحة/ }));
    const dialog = await screen.findByRole('dialog');
    await userEvent.click(within(dialog).getByRole('button', { name: /بدء المصالحة/ }));

    await waitFor(() => expect(callsTo(fetchMock, '/api/v1/queue/jobs/101/reconcile').length).toBe(1));
    expect(String(callsTo(fetchMock, '/api/v1/queue/jobs/101/reconcile')[0][0])).toContain('requeue_if_missing=true');
  });

  it('cancels a waiting job and requires confirmation', async () => {
    const queued = { ...mockJob, status: 'QUEUED' as const };
    const fetchMock = mockFetch({
      '/queue/jobs/101/cancel': () => ({ ok: true, detail: 'Job #101 marked SKIPPED.', job: { ...mockJob, status: 'SKIPPED' } }),
      '/queue/jobs': () => queueResponse(queued),
    });

    renderWithProviders(<QueuePage />);
    await screen.findByTestId('queue-page');

    await userEvent.click(screen.getByRole('button', { name: /إلغاء/ }));
    const dialog = await screen.findByRole('dialog');
    expect(callsTo(fetchMock, '/api/v1/queue/jobs/101/cancel').length).toBe(0);

    await userEvent.click(within(dialog).getByRole('button', { name: /تأكيد الإلغاء/ }));
    await waitFor(() => expect(callsTo(fetchMock, '/api/v1/queue/jobs/101/cancel').length).toBe(1));
  });

  it('filters queue jobs by status tab', async () => {
    const fetchMock = mockFetch({ '/queue/jobs': () => queueResponse() });
    renderWithProviders(<QueuePage />);
    await screen.findByTestId('queue-page');

    await userEvent.click(screen.getByRole('button', { name: /فاشلة/ }));
    await waitFor(() =>
      expect(callsTo(fetchMock, '/api/v1/queue/jobs').some(([u]) => String(u).includes('status=FAILED'))).toBe(true)
    );
  });
});
