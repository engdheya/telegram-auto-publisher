import type {
  AuditLog,
  BackupItem,
  DashboardOverview,
  DatabaseHealth,
  Language,
  MessageEventItem,
  PublishingRoute,
  PublishJobDetail,
  RouteFilterConfig,
  SourceChannel,
  SystemSettingItem,
  TargetChannel,
  TelegramAccountStatus,
  TokenResponse,
  User,
} from '../types';

const TOKEN_KEY = 'tap_access_token';

export function getStoredToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setStoredToken(token: string | null): void {
  if (token) {
    localStorage.setItem(TOKEN_KEY, token);
  } else {
    localStorage.removeItem(TOKEN_KEY);
  }
}

export class ApiError extends Error {
  status: number;
  code?: string;

  constructor(message: string, status: number, code?: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getStoredToken();
  const headers: Record<string, string> = {
    ...(init.body ? { 'Content-Type': 'application/json' } : {}),
    ...(init.headers as Record<string, string> | undefined),
  };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  // Strictly relative path (/api/v1/...) so Vite dev proxy & production reverse proxy both work cleanly
  const resp = await fetch(`/api/v1${path}`, {
    ...init,
    headers,
  });

  if (resp.status === 204) {
    return undefined as T;
  }

  let data: unknown = null;
  const contentType = resp.headers.get('content-type') || '';
  if (contentType.includes('application/json')) {
    data = await resp.json();
  } else {
    const txt = await resp.text();
    data = { detail: txt };
  }

  if (!resp.ok) {
    const errObj = (data || {}) as { detail?: string | Array<{ msg?: string }>; code?: string };
    let msg = `HTTP ${resp.status}`;
    if (typeof errObj.detail === 'string') {
      msg = errObj.detail;
    } else if (Array.isArray(errObj.detail) && errObj.detail.length > 0) {
      msg = errObj.detail.map((e) => e.msg || '').join(', ');
    }
    if (resp.status === 401 && path !== '/auth/login') {
      setStoredToken(null);
      window.dispatchEvent(new CustomEvent('tap:unauthorized'));
    }
    throw new ApiError(msg, resp.status, errObj.code);
  }

  return data as T;
}

export const api = {
  // Auth & Users
  login: (username: string, password: string) =>
    request<TokenResponse>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    }),
  me: () => request<User>('/auth/me'),
  changePassword: (current_password: string, new_password: string) =>
    request<TokenResponse>('/auth/change-password', {
      method: 'POST',
      body: JSON.stringify({ current_password, new_password }),
    }),
  updateLanguage: (preferred_language: Language) =>
    request<User>('/auth/language', {
      method: 'PATCH',
      body: JSON.stringify({ preferred_language }),
    }),
  listUsers: () => request<User[]>('/auth/users'),
  createUser: (payload: {
    username: string;
    email: string;
    password: string;
    role: 'admin' | 'operator';
    preferred_language: Language;
  }) =>
    request<User>('/auth/users', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  // Dashboard
  getDashboardOverview: () => request<DashboardOverview>('/dashboard/overview'),

  // Telegram Account
  getTelegramStatus: () => request<TelegramAccountStatus>('/telegram/status'),
  sendTelegramCode: (payload: {
    label: string;
    api_id: number;
    api_hash: string;
    phone_number: string;
    auto_reconnect: boolean;
  }) =>
    request<TelegramAccountStatus>('/telegram/send-code', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  verifyTelegramCode: (code: string, password?: string) =>
    request<TelegramAccountStatus>('/telegram/verify-code', {
      method: 'POST',
      body: JSON.stringify({ code, password: password || null }),
    }),
  verifyTelegramPassword: (password: string) =>
    request<TelegramAccountStatus>('/telegram/verify-password', {
      method: 'POST',
      body: JSON.stringify({ password }),
    }),
  reconnectTelegram: () =>
    request<TelegramAccountStatus>('/telegram/reconnect', { method: 'POST' }),
  setTelegramAutoReconnect: (auto_reconnect: boolean) =>
    request<TelegramAccountStatus>('/telegram/auto-reconnect', {
      method: 'PATCH',
      body: JSON.stringify({ auto_reconnect }),
    }),
  logoutTelegram: () =>
    request<TelegramAccountStatus>('/telegram/logout', { method: 'POST' }),

  // Sources
  listSources: () => request<SourceChannel[]>('/sources'),
  createSource: (payload: {
    title: string;
    identifier: string;
    invite_link?: string | null;
    is_enabled: boolean;
  }) =>
    request<SourceChannel>('/sources', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  updateSource: (
    id: number,
    payload: Partial<{ title: string; identifier: string; invite_link: string | null; is_enabled: boolean }>
  ) =>
    request<SourceChannel>(`/sources/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),
  verifySource: (id: number) =>
    request<{ accessible: boolean; source: SourceChannel; detail: string }>(
      `/sources/${id}/verify`,
      { method: 'POST' }
    ),
  startSource: (id: number) =>
    request<SourceChannel>(`/sources/${id}/start`, { method: 'POST' }),
  stopSource: (id: number) =>
    request<SourceChannel>(`/sources/${id}/stop`, { method: 'POST' }),
  deleteSource: (id: number) =>
    request<void>(`/sources/${id}`, { method: 'DELETE' }),

  // Targets
  listTargets: () => request<TargetChannel[]>('/targets'),
  createTarget: (payload: {
    title: string;
    identifier: string;
    invite_link?: string | null;
    is_enabled: boolean;
  }) =>
    request<TargetChannel>('/targets', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  updateTarget: (
    id: number,
    payload: Partial<{ title: string; identifier: string; invite_link: string | null; is_enabled: boolean }>
  ) =>
    request<TargetChannel>(`/targets/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),
  verifyTarget: (id: number) =>
    request<{ ok: boolean; target: TargetChannel; detail: string }>(
      `/targets/${id}/verify`,
      { method: 'POST' }
    ),
  testPublishTarget: (id: number, message: string) =>
    request<{ ok: boolean; target: TargetChannel; detail: string; test_message_id: number | null }>(
      `/targets/${id}/test-publish`,
      {
        method: 'POST',
        body: JSON.stringify({ message }),
      }
    ),
  deleteTarget: (id: number) =>
    request<void>(`/targets/${id}`, { method: 'DELETE' }),

  // Routes
  listRoutes: (params?: { source_id?: number; target_id?: number }) => {
    const sp = new URLSearchParams();
    if (params?.source_id) sp.set('source_id', String(params.source_id));
    if (params?.target_id) sp.set('target_id', String(params.target_id));
    const qs = sp.toString();
    return request<PublishingRoute[]>(`/routes${qs ? `?${qs}` : ''}`);
  },
  createRoute: (payload: {
    name: string;
    description?: string | null;
    source_channel_id: number;
    target_channel_id: number;
    is_enabled: boolean;
    priority: number;
    filters: RouteFilterConfig;
  }) =>
    request<PublishingRoute>('/routes', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  createBulkRoutes: (payload: {
    name_prefix: string;
    source_channel_ids: number[];
    target_channel_ids: number[];
    is_enabled: boolean;
    filters: RouteFilterConfig;
  }) =>
    request<PublishingRoute[]>('/routes/bulk', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  updateRoute: (
    id: number,
    payload: Partial<{
      name: string;
      description: string | null;
      is_enabled: boolean;
      priority: number;
      filters: RouteFilterConfig;
    }>
  ) =>
    request<PublishingRoute>(`/routes/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),
  toggleRoute: (id: number) =>
    request<PublishingRoute>(`/routes/${id}/toggle`, { method: 'POST' }),
  deleteRoute: (id: number) =>
    request<void>(`/routes/${id}`, { method: 'DELETE' }),

  // Messages History
  listMessages: (params: {
    page?: number;
    page_size?: number;
    source_id?: number;
    content_type?: string;
    search?: string;
  }) => {
    const sp = new URLSearchParams();
    if (params.page) sp.set('page', String(params.page));
    if (params.page_size) sp.set('page_size', String(params.page_size));
    if (params.source_id) sp.set('source_id', String(params.source_id));
    if (params.content_type) sp.set('content_type', params.content_type);
    if (params.search) sp.set('search', params.search);
    return request<{ total: number; page: number; page_size: number; items: MessageEventItem[] }>(
      `/messages?${sp.toString()}`
    );
  },

  // Queue Management
  listQueueJobs: (params: {
    page?: number;
    page_size?: number;
    status?: string;
    target_id?: number;
    source_id?: number;
  }) => {
    const sp = new URLSearchParams();
    if (params.page) sp.set('page', String(params.page));
    if (params.page_size) sp.set('page_size', String(params.page_size));
    if (params.status) sp.set('status', params.status);
    if (params.target_id) sp.set('target_id', String(params.target_id));
    if (params.source_id) sp.set('source_id', String(params.source_id));
    return request<{
      total: number;
      page: number;
      page_size: number;
      counts_by_status: Record<string, number>;
      items: PublishJobDetail[];
    }>(`/queue/jobs?${sp.toString()}`);
  },
  retryQueueJob: (jobId: number) =>
    request<{ ok: boolean; detail: string; job: PublishJobDetail }>(
      `/queue/jobs/${jobId}/retry`,
      { method: 'POST' }
    ),
  reconcileQueueJob: (jobId: number, requeueIfMissing = true) =>
    request<{ ok: boolean; detail: string; job: PublishJobDetail }>(
      `/queue/jobs/${jobId}/reconcile?requeue_if_missing=${requeueIfMissing}`,
      { method: 'POST' }
    ),
  cancelQueueJob: (jobId: number) =>
    request<{ ok: boolean; detail: string; job: PublishJobDetail }>(
      `/queue/jobs/${jobId}/cancel`,
      { method: 'POST' }
    ),

  // Logs
  listLogs: (params: {
    page?: number;
    page_size?: number;
    level?: string;
    category?: string;
    search?: string;
  }) => {
    const sp = new URLSearchParams();
    if (params.page) sp.set('page', String(params.page));
    if (params.page_size) sp.set('page_size', String(params.page_size));
    if (params.level) sp.set('level', params.level);
    if (params.category) sp.set('category', params.category);
    if (params.search) sp.set('search', params.search);
    return request<{ total: number; page: number; page_size: number; items: AuditLog[] }>(
      `/logs?${sp.toString()}`
    );
  },

  // Settings & Backups
  getSettings: () => request<{ items: SystemSettingItem[] }>('/settings'),
  updateSettings: (settings: Array<{ key: string; value: unknown }>) =>
    request<{ items: SystemSettingItem[] }>('/settings', {
      method: 'PUT',
      body: JSON.stringify({ settings }),
    }),
  getIntegrity: () => request<DatabaseHealth>('/settings/integrity'),
  listBackups: () => request<{ items: BackupItem[] }>('/settings/backups'),
  createBackup: (label?: string) =>
    request<BackupItem>('/settings/backups', {
      method: 'POST',
      body: JSON.stringify({ label: label || null }),
    }),
  restoreBackup: (filename: string) =>
    request<{
      restored_from: string;
      sha256: string;
      pre_restore_backup: string | null;
      restored_at: string;
    }>('/settings/backups/restore', {
      method: 'POST',
      body: JSON.stringify({ filename }),
    }),
  downloadBackupBlob: async (filename: string): Promise<Blob> => {
    const token = getStoredToken();
    const resp = await fetch(`/api/v1/settings/backups/${encodeURIComponent(filename)}/download`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!resp.ok) {
      throw new ApiError('Failed to download backup file', resp.status);
    }
    return resp.blob();
  },
};
