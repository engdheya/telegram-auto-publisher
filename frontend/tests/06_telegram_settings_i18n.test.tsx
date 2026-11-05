import { describe, expect, it } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { TelegramAccountPage } from '../src/pages/TelegramAccountPage';
import { SettingsPage } from '../src/pages/SettingsPage';
import { LogsPage } from '../src/pages/LogsPage';
import { useI18n } from '../src/contexts/I18nContext';
import React from 'react';
import {
  callsTo,
  lastBody,
  mockAuditLog,
  mockFetch,
  mockSettings,
  mockTelegram,
  mockUser,
  renderWithProviders,
} from './helpers';

describe('Telegram account page', () => {
  it('shows a masked, secret-free account status', async () => {
    mockFetch({ '/telegram/status': () => mockTelegram, '/auth/me': () => mockUser });

    renderWithProviders(<TelegramAccountPage />);
    expect(await screen.findByTestId('telegram-page')).toBeInTheDocument();
    expect(screen.getByText('Relay Admin')).toBeInTheDocument();
    expect(screen.getByText(/\+967\*+000/)).toBeInTheDocument();
    expect(screen.getByText('محفوظ ومشفّر')).toBeInTheDocument();
    // API hash value must never be exposed
    expect(screen.queryByText(/0123456789abcdef/)).toBeNull();
  });

  it('requests an OTP and then submits the verification code', async () => {
    let phase: 'idle' | 'awaiting' = 'idle';
    const fetchMock = mockFetch({
      '/telegram/send-code': () => {
        phase = 'awaiting';
        return { ...mockTelegram, auth_state: 'AWAITING_CODE', is_connected: false, has_saved_session: false };
      },
      '/telegram/verify-code': () => ({ ...mockTelegram, auth_state: 'CONNECTED', is_connected: true }),
      '/telegram/status': () =>
        phase === 'idle'
          ? { ...mockTelegram, auth_state: 'UNCONFIGURED', is_connected: false, has_saved_session: false, api_id: null, masked_phone: null, telegram_display_name: null, telegram_username: null }
          : { ...mockTelegram, auth_state: 'AWAITING_CODE', is_connected: false, has_saved_session: false },
      '/auth/me': () => mockUser,
    });

    renderWithProviders(<TelegramAccountPage />);
    await screen.findByTestId('telegram-page');

    const boxes = screen.getAllByRole('textbox');
    await userEvent.type(boxes[0], '1234567'); // label
    await userEvent.type(boxes[1], '1234567'); // API ID
    await userEvent.type(screen.getByLabelText(/^API Hash$/), '0123456789abcdef0123456789abcdef');
    await userEvent.type(boxes[2], '+967700000000'); // phone
    await userEvent.click(screen.getByRole('button', { name: /إرسال رمز التحقق/ }));

    await waitFor(() => expect(callsTo(fetchMock, '/api/v1/telegram/send-code').length).toBe(1));
    expect(lastBody(fetchMock, '/api/v1/telegram/send-code')).toMatchObject({
      api_id: 1234567,
      phone_number: '+967700000000',
    });

    const codeInput = (await screen.findAllByRole('textbox'))[0];
    await userEvent.type(codeInput, '12345');
    await userEvent.click(screen.getByRole('button', { name: /تأكيد الرمز/ }));

    await waitFor(() => expect(callsTo(fetchMock, '/api/v1/telegram/verify-code').length).toBe(1));
    expect(lastBody(fetchMock, '/api/v1/telegram/verify-code')).toEqual({ code: '12345', password: null });
  });

  it('reconnects the saved session through the API', async () => {
    const fetchMock = mockFetch({
      '/telegram/reconnect': () => mockTelegram,
      '/telegram/status': () => mockTelegram,
      '/auth/me': () => mockUser,
    });

    renderWithProviders(<TelegramAccountPage />);
    await screen.findByTestId('telegram-page');

    await userEvent.click(screen.getAllByRole('button', { name: /إعادة الاتصال/ })[0]);
    await waitFor(() => expect(callsTo(fetchMock, '/api/v1/telegram/reconnect').length).toBe(1));
  });
});

describe('Settings page (system, security, backups)', () => {
  const handlers = () => ({
    '/settings/integrity': () => ({
      healthy: true,
      journal_mode: 'wal',
      wal_enabled: true,
      foreign_keys_enabled: true,
      integrity_check: ['ok'],
      foreign_key_violations: [],
      missing_tables: [],
      tables_count: 12,
    }),
    '/settings/backups/restore': () => ({
      restored_from: 'tap_backup_20260101_101010.db',
      sha256: 'abc',
      pre_restore_backup: 'tap_backup_safety.db',
      restored_at: '2026-01-01T10:10:10Z',
    }),
    '/settings/backups': (url: string, init?: RequestInit) =>
      init?.method === 'POST'
        ? { filename: 'tap_backup_20260101_111111.db', size_bytes: 40960, sha256: 'deadbeef', created_at: '2026-01-01T11:11:11Z' }
        : {
            items: [
              { filename: 'tap_backup_20260101_101010.db', size_bytes: 40960, sha256: 'deadbeefdeadbeef', created_at: '2026-01-01T10:10:10Z' },
            ],
          },
    '/auth/language': () => mockUser,
    '/settings': (_url: string, init?: RequestInit) =>
      init?.method === 'PUT' ? { items: mockSettings } : { items: mockSettings },
    '/auth/users': (_url: string, init?: RequestInit) => (init?.method === 'POST' ? mockUser : [mockUser]),
    '/auth/me': () => mockUser,
  });

  it('renders integrity results and creates an online backup', async () => {
    const fetchMock = mockFetch(handlers());
    renderWithProviders(<SettingsPage />);
    await screen.findByTestId('settings-page');

    expect(screen.getByText('journal_mode=wal')).toBeInTheDocument();
    expect(screen.getByText('FK ON')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: /إنشاء نسخة الآن/ }));
    await waitFor(() =>
      expect(callsTo(fetchMock, '/api/v1/settings/backups').filter(([, i]) => i?.method === 'POST').length).toBe(1)
    );
  });

  it('saves numeric/boolean settings with correct types', async () => {
    const fetchMock = mockFetch(handlers());
    renderWithProviders(<SettingsPage />);
    await screen.findByTestId('settings-page');

    const maxAttempts = screen.getByLabelText('أقصى عدد محاولات لكل مهمة');
    await userEvent.clear(maxAttempts);
    await userEvent.type(maxAttempts, '6');
    await userEvent.click(screen.getByRole('button', { name: /حفظ كل الإعدادات/ }));

    await waitFor(() =>
      expect(callsTo(fetchMock, '/api/v1/settings').filter(([, i]) => i?.method === 'PUT').length).toBe(1)
    );
    const body = lastBody(fetchMock, '/api/v1/settings');
    const maxItem = body.settings.find((s: { key: string }) => s.key === 'retry.max_attempts');
    const boolItem = body.settings.find((s: { key: string }) => s.key === 'backup.auto_before_restore');
    expect(maxItem.value).toBe(6);
    expect(boolItem.value).toBe(true);
  });

  it('requires confirmation before restoring a backup and reports the result', async () => {
    const fetchMock = mockFetch(handlers());
    renderWithProviders(<SettingsPage />);
    await screen.findByTestId('settings-page');

    await userEvent.click((await screen.findAllByRole('button', { name: /^استعادة$/ }))[0]);
    const dialog = await screen.findByRole('dialog');
    expect(callsTo(fetchMock, '/api/v1/settings/backups/restore').length).toBe(0);

    await userEvent.click(within(dialog).getByRole('button', { name: /استعادة الآن/ }));
    await waitFor(() => expect(callsTo(fetchMock, '/api/v1/settings/backups/restore').length).toBe(1));
    expect(lastBody(fetchMock, '/api/v1/settings/backups/restore')).toEqual({ filename: 'tap_backup_20260101_101010.db' });
  });

  it('validates password confirmation before calling the API', async () => {
    const fetchMock = mockFetch({ ...handlers(), '/auth/change-password': () => ({ access_token: 'new', token_type: 'bearer', expires_in_seconds: 3600, user: mockUser }) });
    renderWithProviders(<SettingsPage />);
    await screen.findByTestId('settings-page');

    const pwd = screen.getAllByLabelText(/كلمة المرور/, { selector: 'input' });
    await userEvent.type(pwd[0], 'OldPass!2026');
    await userEvent.type(pwd[1], 'NewPass!2026');
    await userEvent.type(pwd[2], 'Mismatch!2026');
    await userEvent.click(screen.getByRole('button', { name: /تحديث كلمة المرور/ }));

    expect(await screen.findByText('كلمتا المرور غير متطابقتين')).toBeInTheDocument();
    expect(callsTo(fetchMock, '/api/v1/auth/change-password').length).toBe(0);
  });
});

describe('Logs page', () => {
  it('filters by level and opens the raw JSON drawer', async () => {
    const fetchMock = mockFetch({
      '/logs': () => ({ total: 1, page: 1, page_size: 30, items: [mockAuditLog] }),
    });

    renderWithProviders(<LogsPage />);
    await screen.findByTestId('logs-page');
    expect(screen.getByText('JOB_PUBLISHED')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: /JSON/ }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText(/"target_message_id": 900/)).toBeInTheDocument();

    await userEvent.click(within(dialog).getByRole('button', { name: /إغلاق/ }));
    await userEvent.selectOptions(screen.getByLabelText('المستوى'), 'ERROR');
    await waitFor(() =>
      expect(callsTo(fetchMock, '/api/v1/logs').some(([u]) => String(u).includes('level=ERROR'))).toBe(true)
    );
  });
});

describe('Internationalisation / RTL', () => {
  const Probe: React.FC = () => {
    const { lang, isRtl, tr } = useI18n();
    return (
      <div>
        <span data-testid="lang">{lang}</span>
        <span data-testid="rtl">{String(isRtl)}</span>
        <span data-testid="dir">{document.documentElement.dir}</span>
        <span data-testid="text">{tr('مرحبا', 'Hello')}</span>
        <button type="button" onClick={() => (window as any).__setLang?.()}>
          noop
        </button>
      </div>
    );
  };

  it('defaults to Arabic RTL and switches the document direction', async () => {
    renderWithProviders(<Probe />);
    expect(screen.getByTestId('lang')).toHaveTextContent('ar');
    expect(screen.getByTestId('rtl')).toHaveTextContent('true');
    await waitFor(() => expect(document.documentElement.dir).toBe('rtl'));
    expect(document.documentElement.lang).toBe('ar');
    expect(screen.getByTestId('text')).toHaveTextContent('مرحبا');
  });
});
