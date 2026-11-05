import React, { useCallback, useEffect, useState } from 'react';
import {
  KeyRound,
  Link2,
  LogOut,
  PhoneCall,
  RefreshCw,
  Send,
  ShieldCheck,
  Smartphone,
  Wifi,
  WifiOff,
} from 'lucide-react';
import { api } from '../services/api';
import type { TelegramAccountStatus } from '../types';
import { useI18n } from '../contexts/I18nContext';
import { useToast } from '../contexts/ToastContext';
import { useAuth } from '../contexts/AuthContext';
import { usePolling } from '../hooks/usePolling';
import { Badge, Button, Card, ConfirmDialog, Input, Spinner, Toggle, formatDateTime } from '../components/ui';

export const TelegramAccountPage: React.FC = () => {
  const { tr, lang } = useI18n();
  const { notify } = useToast();
  const { user } = useAuth();
  const isAdmin = user?.role === 'admin';

  const [status, setStatus] = useState<TelegramAccountStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);

  // login form
  const [label, setLabel] = useState('Primary Telegram Account');
  const [apiId, setApiId] = useState('');
  const [apiHash, setApiHash] = useState('');
  const [phone, setPhone] = useState('');
  const [code, setCode] = useState('');
  const [twoFa, setTwoFa] = useState('');
  const [logoutOpen, setLogoutOpen] = useState(false);

  const load = useCallback(
    async (silent = false) => {
      try {
        const res = await api.getTelegramStatus();
        setStatus(res);
      } catch (err) {
        if (!silent) notify(err instanceof Error ? err.message : 'Failed', 'error');
      } finally {
        setLoading(false);
      }
    },
    [notify]
  );

  useEffect(() => {
    void load();
  }, [load]);

  usePolling(() => load(true), 12000);

  const run = async (key: string, fn: () => Promise<{ status: TelegramAccountStatus } | TelegramAccountStatus>, successMsg: string) => {
    setBusy(key);
    try {
      const res = await fn();
      const next = 'status' in (res as object) ? (res as { status: TelegramAccountStatus }).status : (res as TelegramAccountStatus);
      if (next && 'auth_state' in next) setStatus(next);
      notify(successMsg, 'success');
      await load(true);
    } catch (err) {
      notify(err instanceof Error ? err.message : 'Operation failed', 'error');
    } finally {
      setBusy(null);
    }
  };

  if (loading) return <Spinner label={tr('جاري تحميل حالة الحساب...', 'Loading account status...')} />;

  const authState = status?.auth_state || 'UNCONFIGURED';
  const awaitingCode = authState === 'AWAITING_CODE';
  const awaitingPassword = authState === 'AWAITING_PASSWORD';
  const connected = !!status?.is_connected;

  return (
    <div className="space-y-5" data-testid="telegram-page">
      <div>
        <h1 className="text-xl font-bold text-slate-50">{tr('حساب تيليجرام', 'Telegram Account')}</h1>
        <p className="mt-0.5 text-xs text-slate-500">
          {tr(
            'ربط حساب MTProto عبر API ID/Hash وتسجيل الدخول برمز التحقق. تُخزَّن الجلسة مشفرة ولا تُعرض أبدًا في الواجهة.',
            'Link an MTProto account with API ID/Hash and OTP verification. The session is stored encrypted and never exposed in the UI.'
          )}
        </p>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2" title={tr('حالة الاتصال', 'Connection Status')}>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="flex items-center gap-3 rounded-xl border border-slate-800 bg-slate-950/50 p-3">
              {connected ? <Wifi className="h-5 w-5 text-emerald-400" /> : <WifiOff className="h-5 w-5 text-rose-400" />}
              <div>
                <p className="text-sm font-semibold text-slate-100">
                  {connected ? tr('متصل', 'Connected') : tr('غير متصل', 'Disconnected')}
                </p>
                <p className="text-[11px] text-slate-500">
                  auth_state: <span className="font-mono">{authState}</span>
                </p>
              </div>
            </div>

            <div className="rounded-xl border border-slate-800 bg-slate-950/50 p-3">
              <p className="text-[11px] text-slate-500">{tr('الحساب', 'Account')}</p>
              <p className="truncate text-sm font-semibold text-slate-100">
                {status?.telegram_display_name || '—'}
              </p>
              <p className="truncate text-[11px] text-slate-500">
                @{status?.telegram_username || '—'} · {status?.masked_phone || '—'}
              </p>
            </div>

            <div className="rounded-xl border border-slate-800 bg-slate-950/50 p-3">
              <p className="text-[11px] text-slate-500">{tr('API ID', 'API ID')}</p>
              <p className="font-mono text-sm text-slate-100">{status?.api_id ?? '—'}</p>
              <p className="text-[11px] text-slate-500">
                API Hash: {status?.has_api_hash ? tr('مخزَّن مشفرًا ✓', 'stored encrypted ✓') : '—'}
              </p>
            </div>

            <div className="rounded-xl border border-slate-800 bg-slate-950/50 p-3">
              <p className="text-[11px] text-slate-500">{tr('ملف الجلسة', 'Session file')}</p>
              <p className="text-sm text-slate-100">
                {status?.has_saved_session ? tr('محفوظ ومشفّر', 'Saved & encrypted') : tr('غير موجود', 'Not saved')}
              </p>
              <p className="text-[11px] text-slate-500">
                {tr('إعادة المحاولة التلقائية', 'Auto reconnect')}: {status?.auto_reconnect ? 'ON' : 'OFF'}
              </p>
            </div>
          </div>

          <div className="mt-4 grid gap-2 text-[11px] text-slate-500 sm:grid-cols-2">
            <p>{tr('آخر اتصال:', 'Last connected:')} {formatDateTime(status?.last_connected_at, lang)}</p>
            <p>{tr('آخر انقطاع:', 'Last disconnected:')} {formatDateTime(status?.last_disconnected_at, lang)}</p>
            <p>{tr('آخر نبضة:', 'Heartbeat:')} {formatDateTime(status?.heartbeat_at, lang)}</p>
            <p>{tr('محاولات إعادة الاتصال:', 'Reconnect attempts:')} {status?.reconnect_attempts ?? 0}</p>
          </div>

          {status?.last_error && (
            <div className="mt-4 rounded-lg border border-rose-800/60 bg-rose-950/40 px-3 py-2 text-xs text-rose-300">
              {tr('آخر خطأ:', 'Last error:')} {status.last_error}
            </div>
          )}

          <div className="mt-5 flex flex-wrap items-center gap-2">
            <Button
              variant="secondary"
              disabled={!isAdmin}
              loading={busy === 'reconnect'}
              icon={<RefreshCw className="h-4 w-4" />}
              onClick={() =>
                run('reconnect', () => api.reconnectTelegram(), tr('تمت إعادة الاتصال', 'Reconnected successfully'))
              }
            >
              {tr('إعادة الاتصال', 'Reconnect')}
            </Button>
            <Button
              variant="danger"
              disabled={!isAdmin || connected === false && authState === 'UNCONFIGURED'}
              loading={busy === 'logout'}
              icon={<LogOut className="h-4 w-4" />}
              onClick={() => setLogoutOpen(true)}
            >
              {tr('تسجيل الخروج وإلغاء الربط', 'Logout & Unlink')}
            </Button>
            <div className="ms-auto flex items-center gap-2">
              <span className="text-[11px] text-slate-400">{tr('إعادة الاتصال التلقائية', 'Auto reconnect')}</span>
              <Toggle
                checked={!!status?.auto_reconnect}
                disabled={!isAdmin}
                onChange={(next) =>
                  run(
                    'auto',
                    () => api.setTelegramAutoReconnect(next),
                    tr('تم تحديث إعداد إعادة الاتصال', 'Auto reconnect preference updated')
                  )
                }
              />
            </div>
          </div>
          {!isAdmin && (
            <p className="mt-3 text-[11px] text-amber-400">
              {tr('إدارة الحساب متاحة لصلاحية Admin فقط.', 'Account management requires the Admin role.')}
            </p>
          )}
        </Card>

        <Card title={tr('ربط الحساب', 'Link Account')}>
          {!connected && !awaitingCode && !awaitingPassword && (
            <div className="space-y-3">
              <Input label={tr('اسم تعريفي', 'Label')} value={label} onChange={(e) => setLabel(e.target.value)} />
              <Input
                label="API ID"
                inputMode="numeric"
                value={apiId}
                onChange={(e) => setApiId(e.target.value.replace(/\D/g, ''))}
                placeholder="1234567"
              />
              <Input
                label="API Hash"
                type="password"
                value={apiHash}
                onChange={(e) => setApiHash(e.target.value)}
                placeholder="0123456789abcdef0123456789abcdef"
              />
              <Input
                label={tr('رقم الهاتف (دولي)', 'Phone number (international)')}
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                placeholder="+967700000000"
              />
              <Button
                className="w-full"
                disabled={!isAdmin}
                loading={busy === 'send'}
                icon={<PhoneCall className="h-4 w-4" />}
                onClick={() =>
                  run(
                    'send',
                    () =>
                      api.sendTelegramCode({
                        label: label.trim() || 'Primary Telegram Account',
                        api_id: Number(apiId),
                        api_hash: apiHash.trim(),
                        phone_number: phone.trim(),
                        auto_reconnect: true,
                      }),
                    tr('تم إرسال رمز التحقق إلى تطبيق تيليجرام', 'Verification code sent to your Telegram app')
                  )
                }
              >
                {tr('إرسال رمز التحقق', 'Send login code')}
              </Button>
              <p className="text-[11px] leading-relaxed text-slate-500">
                {tr(
                  'احصل على API ID/Hash من my.telegram.org. لن يظهر رمز التحقق ولا كلمة مرور التحقق بخطوتين في السجلات.',
                  'Get API ID/Hash from my.telegram.org. OTP codes and 2FA passwords are never written to logs.'
                )}
              </p>
            </div>
          )}

          {awaitingCode && (
            <div className="space-y-3">
              <div className="rounded-lg border border-cyan-800/60 bg-cyan-950/40 px-3 py-2 text-[11px] text-cyan-300">
                {tr('تم إرسال الرمز إلى', 'Code sent to')} {status?.masked_phone || phone || '—'}
              </div>
              <Input
                label={tr('رمز التحقق', 'Verification code')}
                value={code}
                onChange={(e) => setCode(e.target.value.trim())}
                inputMode="numeric"
                placeholder="12345"
                autoComplete="one-time-code"
              />
              <Button
                className="w-full"
                loading={busy === 'verify'}
                disabled={!code}
                icon={<ShieldCheck className="h-4 w-4" />}
                onClick={async () => {
                  setBusy('verify');
                  try {
                    const res = await api.verifyTelegramCode(code);
                    setStatus(res);
                    setCode('');
                    if (res.auth_state === 'AWAITING_PASSWORD') {
                      notify(tr('الحساب محمي بكلمة مرور تحقق بخطوتين', 'Account is protected by a 2FA password'), 'warning');
                    } else {
                      notify(tr('تم تسجيل الدخول بنجاح', 'Signed in successfully'), 'success');
                    }
                  } catch (err) {
                    notify(err instanceof Error ? err.message : 'Failed', 'error');
                  } finally {
                    setBusy(null);
                  }
                }}
              >
                {tr('تأكيد الرمز', 'Verify code')}
              </Button>
            </div>
          )}

          {(awaitingPassword || (awaitingCode && twoFa)) && (
            <div className="mt-3 space-y-3 border-t border-slate-800 pt-3">
              <Input
                label={tr('كلمة مرور التحقق بخطوتين', 'Two-step verification password')}
                type="password"
                value={twoFa}
                onChange={(e) => setTwoFa(e.target.value)}
              />
              <Button
                className="w-full"
                loading={busy === 'pwd'}
                disabled={!twoFa || !isAdmin}
                icon={<KeyRound className="h-4 w-4" />}
                onClick={async () => {
                  setBusy('pwd');
                  try {
                    const res = await api.verifyTelegramPassword(twoFa);
                    setStatus(res);
                    setTwoFa('');
                    notify(tr('تم تسجيل الدخول بنجاح', 'Signed in successfully'), 'success');
                  } catch (err) {
                    notify(err instanceof Error ? err.message : 'Failed', 'error');
                  } finally {
                    setBusy(null);
                  }
                }}
              >
                {tr('تأكيد كلمة المرور', 'Submit password')}
              </Button>
            </div>
          )}

          {connected && (
            <div className="space-y-3">
              <div className="flex items-center gap-2 rounded-lg border border-emerald-800/60 bg-emerald-950/40 px-3 py-2 text-[11px] text-emerald-300">
                <Link2 className="h-4 w-4" />
                {tr('الحساب مربوط وجاهز لمراقبة القنوات والنشر', 'Account linked and ready for monitoring & publishing')}
              </div>
              <div className="flex items-center gap-2 text-[11px] text-slate-500">
                <Smartphone className="h-4 w-4" />
                {tr('لإعادة الربط بحساب آخر، قم بتسجيل الخروج أولًا.', 'To relink another account, log out first.')}
              </div>
            </div>
          )}
        </Card>
      </div>

      <Card title={tr('ملاحظات أمنية', 'Security Notes')}>
        <ul className="space-y-2 text-[11px] leading-relaxed text-slate-400">
          <li>
            • {tr(
              'يُشفَّر API Hash وملف الجلسة باستخدام Fernet (AES-128-CBC + HMAC) بمفتاح من متغيرات البيئة.',
              'API Hash and session files are encrypted with Fernet using a key sourced from environment variables.'
            )}
          </li>
          <li>
            • {tr(
              'لا يتم إرجاع API Hash أو بيانات الجلسة في أي استجابة API؛ الواجهة تعرض حالة التخزين فقط.',
              'API Hash and session data are never returned by the API; the UI only shows storage status.'
            )}
          </li>
          <li>
            • {tr(
              'رموز التحقق وكلمات المرور تُخفى من السجلات عبر RedactingFilter.',
              'OTP codes and passwords are redacted from logs by a RedactingFilter.'
            )}
          </li>
        </ul>
        {status?.has_saved_session && (
          <div className="mt-3 flex items-center gap-2">
            <Badge tone="green">{tr('جلسة مشفّرة محفوظة', 'Encrypted session persisted')}</Badge>
            <Badge tone="slate">auth_state: {authState}</Badge>
          </div>
        )}
      </Card>

      <ConfirmDialog
        open={logoutOpen}
        title={tr('تسجيل الخروج من تيليجرام', 'Logout from Telegram')}
        message={tr(
          'سيتم حذف ملف الجلسة المشفّر وإلغاء ربط الحساب. ستتوقف المراقبة والنشر حتى تعيد الربط. هل تريد المتابعة؟',
          'The encrypted session will be deleted and the account unlinked. Monitoring and publishing stop until you relink. Continue?'
        )}
        confirmLabel={tr('تأكيد الخروج', 'Confirm logout')}
        cancelLabel={tr('إلغاء', 'Cancel')}
        loading={busy === 'logout'}
        onCancel={() => setLogoutOpen(false)}
        onConfirm={async () => {
          setLogoutOpen(false);
          await run('logout', () => api.logoutTelegram(), tr('تم تسجيل الخروج', 'Logged out successfully'));
        }}
      />
    </div>
  );
};
