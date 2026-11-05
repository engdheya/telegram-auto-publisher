import React from 'react';
import { MemoryRouter } from 'react-router-dom';
import { render } from '@testing-library/react';
import { vi } from 'vitest';
import { AuthProvider } from '../src/contexts/AuthContext';
import { I18nProvider } from '../src/contexts/I18nContext';
import { ToastProvider } from '../src/contexts/ToastContext';
import type {
  AuditLog,
  DashboardOverview,
  MessageEventItem,
  PublishingRoute,
  PublishJobDetail,
  SourceChannel,
  SystemSettingItem,
  TargetChannel,
  TelegramAccountStatus,
  User,
} from '../src/types';

export const mockUser: User = {
  id: 1,
  username: 'admin',
  email: 'admin@tap.local',
  role: 'admin',
  is_active: true,
  preferred_language: 'ar',
  last_login_at: '2026-01-01T10:00:00Z',
  created_at: '2026-01-01T09:00:00Z',
};

export const mockTelegram: TelegramAccountStatus = {
  id: 1,
  label: 'Primary Telegram Account',
  api_id: 1234567,
  has_api_hash: true,
  masked_phone: '+967******000',
  has_saved_session: true,
  auth_state: 'CONNECTED',
  telegram_user_id: 777,
  telegram_username: 'admin_relay',
  telegram_display_name: 'Relay Admin',
  is_connected: true,
  live_transport_connected: true,
  auto_reconnect: true,
  reconnect_attempts: 0,
  last_connected_at: '2026-01-01T10:00:00Z',
  last_disconnected_at: null,
  heartbeat_at: '2026-01-01T10:05:00Z',
  last_error: null,
  updated_at: '2026-01-01T10:05:00Z',
};

export const mockSource: SourceChannel = {
  id: 11,
  title: 'Source A',
  identifier: '@source_a',
  username: 'source_a',
  telegram_peer_id: -1001234567890,
  invite_link: null,
  is_enabled: true,
  monitoring_status: 'ACTIVE',
  baseline_message_id: 500,
  last_processed_message_id: 512,
  last_processed_at: '2026-01-01T10:00:00Z',
  noforwards_protected: false,
  access_verified_at: '2026-01-01T09:30:00Z',
  last_error: null,
  created_at: '2026-01-01T09:00:00Z',
  updated_at: '2026-01-01T10:00:00Z',
};

export const mockTarget: TargetChannel = {
  id: 21,
  title: 'Target 1',
  identifier: '@target_1',
  username: 'target_1',
  telegram_peer_id: -1009876543210,
  invite_link: null,
  is_enabled: true,
  permission_status: 'VERIFIED',
  can_post_messages: true,
  can_post_media: true,
  last_verified_at: '2026-01-01T09:35:00Z',
  last_test_post_at: null,
  last_error: null,
  created_at: '2026-01-01T09:00:00Z',
  updated_at: '2026-01-01T09:35:00Z',
};

export const mockRoute: PublishingRoute = {
  id: 31,
  name: 'Source A → Target 1',
  description: null,
  source_channel_id: 11,
  source_title: 'Source A',
  source_identifier: '@source_a',
  target_channel_id: 21,
  target_title: 'Target 1',
  target_identifier: '@target_1',
  is_enabled: true,
  priority: 100,
  filters: {
    allowed_content_types: ['text', 'photo', 'video', 'document', 'audio', 'voice', 'album'],
    include_keywords: [],
    exclude_keywords: ['promo'],
    allowed_extensions: [],
    min_text_length: null,
    max_text_length: null,
    prefix_text: null,
    suffix_text: null,
    target_signature: '@target_1',
    strip_urls: false,
  },
  created_at: '2026-01-01T09:40:00Z',
  updated_at: '2026-01-01T09:40:00Z',
};

export const mockJob: PublishJobDetail = {
  id: 101,
  message_event_id: 51,
  route_id: 31,
  route_name: 'Source A → Target 1',
  source_channel_id: 11,
  source_title: 'Source A',
  target_channel_id: 21,
  target_title: 'Target 1',
  status: 'PUBLISHED',
  transformed_text: 'Hello world\n@target_1',
  target_message_id: 900,
  target_message_ids: [900],
  attempts_count: 1,
  max_attempts: 4,
  next_retry_at: null,
  skip_reason: null,
  last_error: null,
  unknown_reason: null,
  reconciliation_checked_at: null,
  published_at: '2026-01-01T10:01:00Z',
  created_at: '2026-01-01T10:00:00Z',
  updated_at: '2026-01-01T10:01:00Z',
  content_type: 'text',
  raw_text: 'Hello world',
  grouped_id: null,
  album_item_count: 1,
  attempts: [
    {
      id: 1,
      attempt_number: 1,
      worker_id: 'worker-1',
      started_at: '2026-01-01T10:00:30Z',
      finished_at: '2026-01-01T10:01:00Z',
      outcome: 'SUCCESS',
      error_code: null,
      error_message: null,
    },
  ],
};

export const mockMessage: MessageEventItem = {
  id: 51,
  source_channel_id: 11,
  source_title: 'Source A',
  telegram_message_id: 512,
  grouped_id: null,
  content_type: 'text',
  raw_text: 'Hello world',
  is_protected_content: false,
  protection_reason: null,
  album_status: 'COMPLETE',
  album_item_count: 1,
  source_published_at: '2026-01-01T10:00:00Z',
  received_at: '2026-01-01T10:00:01Z',
  enqueued_at: '2026-01-01T10:00:02Z',
  media_items: [],
  jobs: [
    {
      id: 101,
      message_event_id: 51,
      route_id: 31,
      route_name: 'Source A → Target 1',
      source_channel_id: 11,
      source_title: 'Source A',
      target_channel_id: 21,
      target_title: 'Target 1',
      status: 'PUBLISHED',
      transformed_text: 'Hello world\n@target_1',
      target_message_id: 900,
      target_message_ids: [900],
      attempts_count: 1,
      max_attempts: 4,
      next_retry_at: null,
      skip_reason: null,
      last_error: null,
      unknown_reason: null,
      reconciliation_checked_at: null,
      published_at: '2026-01-01T10:01:00Z',
      created_at: '2026-01-01T10:00:00Z',
      updated_at: '2026-01-01T10:01:00Z',
    },
  ],
};

export const mockAuditLog: AuditLog = {
  id: 1,
  level: 'INFO',
  category: 'PUBLISHER',
  action: 'JOB_PUBLISHED',
  actor_user_id: 1,
  actor_username: 'admin',
  entity_type: 'publish_job',
  entity_id: '101',
  message: 'Published job #101 to Target 1',
  details: { target_message_id: 900 },
  ip_address: null,
  created_at: '2026-01-01T10:01:00Z',
};

export const mockSettings: SystemSettingItem[] = [
  { key: 'ui.default_language', value: 'ar', category: 'general', description: 'Default language', updated_by: 'system', updated_at: null },
  { key: 'retry.max_attempts', value: 4, category: 'retry', description: 'Max attempts', updated_by: 'system', updated_at: null },
  { key: 'retry.base_seconds', value: 15, category: 'retry', description: 'Base backoff', updated_by: 'system', updated_at: null },
  { key: 'backup.auto_before_restore', value: true, category: 'backup', description: 'Auto snapshot', updated_by: 'system', updated_at: null },
];

export const mockDashboard: DashboardOverview = {
  telegram_connected: true,
  telegram_auth_state: 'CONNECTED',
  telegram_display_name: 'Relay Admin',
  telegram_username: 'admin_relay',
  worker_alive: true,
  worker_last_heartbeat: '2026-01-01T10:05:00Z',
  sources_total: 1,
  sources_active: 1,
  targets_total: 1,
  targets_verified: 1,
  routes_total: 1,
  routes_active: 1,
  messages_received_total: 12,
  jobs_published: 9,
  jobs_failed: 1,
  jobs_waiting: 2,
  jobs_processing: 0,
  jobs_skipped: 1,
  jobs_unknown: 1,
  database_health: {
    healthy: true,
    journal_mode: 'wal',
    wal_enabled: true,
    foreign_keys_enabled: true,
    integrity_check: ['ok'],
    foreign_key_violations: [],
    missing_tables: [],
    tables_count: 12,
  },
  recent_activities: [mockAuditLog],
};

/* ------------------------------------------------------------------ */
/* fetch mock router                                                   */
/* ------------------------------------------------------------------ */
export type RouteHandler = (url: string, init?: RequestInit) => unknown;

export function jsonResponse(data: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: {
      get: (name: string) =>
        name.toLowerCase() === 'content-type' ? 'application/json' : null,
    },
    json: async () => data,
    text: async () => JSON.stringify(data),
    blob: async () => ({ size: 1024, type: 'application/x-sqlite3' }) as Blob,
  } as unknown as Response;
}

/**
 * Minimal fetch router: the first handler whose URL substring matches wins.
 * More specific substrings must be declared before generic ones.
 */
export function mockFetch(handlers: Record<string, RouteHandler>) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input.toString();
    const key = Object.keys(handlers).find((pattern) => url.includes(pattern));
    if (!key) {
      return jsonResponse({ detail: `No mock handler for ${url}` }, 404);
    }
    const result = handlers[key](url, init);
    return jsonResponse(result ?? {}, 200);
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

export function callsTo(fetchMock: ReturnType<typeof mockFetch>, fragment: string) {
  return fetchMock.mock.calls.filter(([input]) => String(input).includes(fragment));
}

export function lastBody(fetchMock: ReturnType<typeof mockFetch>, fragment: string): any {
  const calls = callsTo(fetchMock, fragment);
  for (let i = calls.length - 1; i >= 0; i -= 1) {
    const init = calls[i][1];
    if (init && typeof init.body === 'string') return JSON.parse(init.body);
  }
  return null;
}

export function renderWithProviders(ui: React.ReactElement, { route = '/' } = {}) {
  return render(
    <MemoryRouter initialEntries={[route]}>
      <I18nProvider>
        <ToastProvider>
          <AuthProvider>{ui}</AuthProvider>
        </ToastProvider>
      </I18nProvider>
    </MemoryRouter>
  );
}
