import React, { useCallback, useEffect, useState } from 'react';
import {
  Database,
  Download,
  HardDriveDownload,
  Languages,
  KeyRound,
  Plus,
  RefreshCw,
  Save,
  ShieldCheck,
  UploadCloud,
  UserPlus,
  Users,
} from 'lucide-react';
import { api } from '../services/api';
import type { BackupItem, DatabaseHealth, SystemSettingItem, User } from '../types';
import { useI18n } from '../contexts/I18nContext';
import { useToast } from '../contexts/ToastContext';
import { useAuth } from '../contexts/AuthContext';
import {
  Badge,
  Button,
  Card,
  ConfirmDialog,
  EmptyState,
  Input,
  Modal,
  Select,
  Spinner,
  formatBytes,
  formatDateTime,
} from '../components/ui';

type SettingDraft = Record<string, string | number | boolean | null>;

const SETTING_LABELS: Record<string, { ar: string; en: string; type: 'text' | 'number' | 'bool' | 'lang' }> = {
  'ui.default_language': { ar: 'اللغة الافتراضية للواجهة', en: 'Default interface language', type: 'lang' },
  'retry.max_attempts': { ar: 'أقصى عدد محاولات لكل مهمة', en: 'Max attempts per job', type: 'number' },
  'retry.base_seconds': { ar: 'زمن الانتظار الأولي (ثانية)', en: 'Base backoff (seconds)', type: 'number' },
  'retry.max_seconds': { ar: 'حد أقصى للانتظار (ثانية)', en: 'Max backoff cap (seconds)', type: 'number' },
  'album.window_ms': { ar: 'نافذة تجميع الألبوم (ملي ثانية)', en: 'Album aggregation window (ms)', type: 'number' },
  'storage.media_retention_hours': { ar: 'مدة الاحتفاظ بملفات الوسائط (ساعة)', en: 'Media cache retention (hours)', type: 'number' },
  'security.session_expire_minutes': { ar: 'مدة صلاحية جلسة الدخول (دقيقة)', en: 'Session expiry (minutes)', type: 'number' },
  'backup.auto_before_restore': { ar: 'نسخة أمان تلقائية قبل الاستعادة', en: 'Auto safety snapshot before restore', type: 'bool' },
};

export const SettingsPage: React.FC = () => {
  const { t, tr, lang, setLang } = useI18n();
  const { notify } = useToast();
  const { user, setUserFromToken } = useAuth();
  const isAdmin = user?.role === 'admin';

  const [settings, setSettings] = useState<SystemSettingItem[]>([]);
  const [draft, setDraft] = useState<SettingDraft>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const [health, setHealth] = useState<DatabaseHealth | null>(null);
  const [checking, setChecking] = useState(false);
  const [backups, setBackups] = useState<BackupItem[]>([]);
  const [backupLabel, setBackupLabel] = useState('');
  const [creatingBackup, setCreatingBackup] = useState(false);
  const [restoreTarget, setRestoreTarget] = useState<BackupItem | null>(null);
  const [restoring, setRestoring] = useState(false);

  const [pwdForm, setPwdForm] = useState({ current: '', next: '', confirm: '' });
  const [changingPwd, setChangingPwd] = useState(false);

  const [users, setUsers] = useState<User[]>([]);
  const [userModal, setUserModal] = useState(false);
  const [newUser, setNewUser] = useState({
    username: '',
    email: '',
    password: '',
    role: 'operator' as 'admin' | 'operator',
    preferred_language: lang,
  });
  const [creatingUser, setCreatingUser] = useState(false);

  const loadSettings = useCallback(async () => {
    try {
      const res = await api.getSettings();
      setSettings(res.items);
      const d: SettingDraft = {};
      res.items.forEach((s) => {
        d[s.key] = s.value as string | number | boolean | null;
      });
      setDraft(d);
    } catch (err) {
      notify(err instanceof Error ? err.message : 'Failed to load settings', 'error');
    } finally {
      setLoading(false);
    }
  }, [notify]);

  const loadBackups = useCallback(async () => {
    if (!isAdmin) return;
    try {
      const res = await api.listBackups();
      setBackups(res.items);
    } catch {
      /* admin-only endpoint; ignore for operators */
    }
  }, [isAdmin]);

  const loadHealth = useCallback(async () => {
    setChecking(true);
    try {
      setHealth(await api.getIntegrity());
    } catch (err) {
      notify(err instanceof Error ? err.message : 'Integrity check failed', 'error');
    } finally {
      setChecking(false);
    }
  }, [notify]);

  const loadUsers = useCallback(async () => {
    if (!isAdmin) return;
    try {
      setUsers(await api.listUsers());
    } catch {
      /* ignore */
    }
  }, [isAdmin]);

  useEffect(() => {
    void loadSettings();
    void loadHealth();
    void loadBackups();
    void loadUsers();
  }, [loadSettings, loadHealth, loadBackups, loadUsers]);

  const saveSettings = async () => {
    setSaving(true);
    try {
      const payload = settings.map((s) => {
        const original = SETTING_LABELS[s.key]?.type;
        let value: unknown = draft[s.key];
        if (original === 'number') value = Number(value);
        if (original === 'bool') value = Boolean(value);
        return { key: s.key, value };
      });
      const res = await api.updateSettings(payload);
      setSettings(res.items);
      notify(tr('تم حفظ الإعدادات', 'Settings saved'), 'success');
    } catch (err) {
      notify(err instanceof Error ? err.message : 'Save failed', 'error');
    } finally {
      setSaving(false);
    }
  };

  const changePassword = async (e: React.FormEvent) => {
    e.preventDefault();
    if (pwdForm.next !== pwdForm.confirm) {
      notify(tr('كلمتا المرور غير متطابقتين', 'Passwords do not match'), 'error');
      return;
    }
    if (pwdForm.next.length < 8) {
      notify(tr('كلمة المرور يجب أن تكون 8 أحرف على الأقل', 'Password must be at least 8 characters'), 'error');
      return;
    }
    setChangingPwd(true);
    try {
      const res = await api.changePassword(pwdForm.current, pwdForm.next);
      if (user) setUserFromToken(res.access_token, res.user);
      setPwdForm({ current: '', next: '', confirm: '' });
      notify(tr('تم تغيير كلمة المرور وإنهاء الجلسات الأخرى', 'Password changed and other sessions revoked'), 'success');
    } catch (err) {
      notify(err instanceof Error ? err.message : 'Change failed', 'error');
    } finally {
      setChangingPwd(false);
    }
  };

  const downloadBackup = async (filename: string) => {
    try {
      const blob = await api.downloadBackupBlob(filename);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      notify(tr('تم تنزيل النسخة الاحتياطية', 'Backup downloaded'), 'success');
    } catch (err) {
      notify(err instanceof Error ? err.message : 'Download failed', 'error');
    }
  };

  const grouped = settings.reduce<Record<string, SystemSettingItem[]>>((acc, s) => {
    acc[s.category] = acc[s.category] ? [...acc[s.category], s] : [s];
    return acc;
  }, {});

  const categoryLabel = (c: string) =>
    ({
      general: tr('عام', 'General'),
      retry: tr('سياسة إعادة المحاولة', 'Retry policy'),
      storage: tr('التخزين', 'Storage'),
      security: tr('الأمان', 'Security'),
      backup: tr('النسخ الاحتياطي', 'Backup'),
    }[c] || c);

  if (loading) return <Spinner label={tr('جاري تحميل الإعدادات...', 'Loading settings...')} />;

  return (
    <div className="space-y-5" data-testid="settings-page">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-slate-50">{tr('الإعدادات والنظام', 'Settings & System')}</h1>
          <p className="mt-0.5 text-xs text-slate-500">
            {tr(
              'إعدادات النظام واللغة وسياسة إعادة المحاولة والتخزين والأمان والنسخ الاحتياطي والاستعادة.',
              'System, language, retry policy, storage, security, database integrity and backup/restore.'
            )}
          </p>
        </div>
        <Button loading={saving} disabled={!isAdmin} icon={<Save className="h-4 w-4" />} onClick={saveSettings}>
          {tr('حفظ كل الإعدادات', 'Save all settings')}
        </Button>
      </div>

      {/* Language + settings */}
      <Card
        title={tr('إعدادات النظام', 'System settings')}
        subtitle={isAdmin ? undefined : tr('التعديل متاح لصلاحية Admin فقط.', 'Editing requires the Admin role.')}
        actions={
          <Button size="sm" variant="secondary" icon={<Languages className="h-3.5 w-3.5" />} onClick={() => setLang(lang === 'ar' ? 'en' : 'ar')}>
            {lang === 'ar' ? 'English UI' : 'واجهة عربية'}
          </Button>
        }
      >
        <div className="grid gap-4 md:grid-cols-2">
          {Object.entries(grouped).map(([category, items]) => (
            <div key={category} className="rounded-xl border border-slate-800 bg-slate-950/40 p-3">
              <p className="mb-2 text-xs font-semibold text-cyan-300">{categoryLabel(category)}</p>
              <div className="space-y-2.5">
                {items.map((s) => {
                  const meta = SETTING_LABELS[s.key];
                  const label = meta ? tr(meta.ar, meta.en) : s.key;
                  const type = meta?.type || 'text';
                  return (
                    <div key={s.key}>
                      {type === 'bool' ? (
                        <label className="flex items-center justify-between gap-2 text-xs text-slate-300">
                          <span>{label}</span>
                          <input
                            type="checkbox"
                            className="h-4 w-4 accent-cyan-500"
                            checked={Boolean(draft[s.key])}
                            disabled={!isAdmin}
                            onChange={(e) => setDraft({ ...draft, [s.key]: e.target.checked })}
                          />
                        </label>
                      ) : type === 'lang' ? (
                        <Select
                          label={label}
                          value={String(draft[s.key] ?? 'ar')}
                          disabled={!isAdmin}
                          onChange={(e) => setDraft({ ...draft, [s.key]: e.target.value })}
                        >
                          <option value="ar">العربية</option>
                          <option value="en">English</option>
                        </Select>
                      ) : (
                        <Input
                          label={label}
                          type={type === 'number' ? 'number' : 'text'}
                          value={String(draft[s.key] ?? '')}
                          disabled={!isAdmin}
                          onChange={(e) =>
                            setDraft({ ...draft, [s.key]: type === 'number' ? Number(e.target.value) : e.target.value })
                          }
                          hint={s.description || undefined}
                        />
                      )}
                      <p className="mt-0.5 text-[10px] text-slate-600">{s.key}</p>
                    </div>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      </Card>

      {/* Security: password change */}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card title={tr('تغيير كلمة المرور', 'Change password')} subtitle={tr('يُعاد إصدار جميع الجلسات عند التغيير.', 'All sessions are re-issued on change.')}>
          <form onSubmit={changePassword} className="space-y-3">
            <Input
              label={tr('كلمة المرور الحالية', 'Current password')}
              type="password"
              value={pwdForm.current}
              onChange={(e) => setPwdForm({ ...pwdForm, current: e.target.value })}
              required
              autoComplete="current-password"
            />
            <Input
              label={tr('كلمة المرور الجديدة', 'New password')}
              type="password"
              value={pwdForm.next}
              onChange={(e) => setPwdForm({ ...pwdForm, next: e.target.value })}
              required
              minLength={8}
              autoComplete="new-password"
              hint={tr('8 أحرف على الأقل، مع أرقام ورموز.', 'At least 8 characters including digits and symbols.')}
            />
            <Input
              label={tr('تأكيد كلمة المرور', 'Confirm new password')}
              type="password"
              value={pwdForm.confirm}
              onChange={(e) => setPwdForm({ ...pwdForm, confirm: e.target.value })}
              required
              minLength={8}
              autoComplete="new-password"
            />
            <Button type="submit" loading={changingPwd} icon={<KeyRound className="h-4 w-4" />}>
              {tr('تحديث كلمة المرور', 'Update password')}
            </Button>
          </form>
        </Card>

        <Card
          title={tr('فحص سلامة قاعدة البيانات', 'Database integrity')}
          actions={
            <Button size="sm" variant="secondary" loading={checking} icon={<RefreshCw className="h-3.5 w-3.5" />} onClick={loadHealth}>
              {tr('فحص الآن', 'Check now')}
            </Button>
          }
        >
          {!health ? (
            <Spinner />
          ) : (
            <div className="space-y-2 text-xs">
              <div className="flex flex-wrap gap-1.5">
                <Badge tone={health.healthy ? 'green' : 'red'}>
                  <ShieldCheck className="h-3 w-3" /> {health.healthy ? tr('سليمة', 'Healthy') : tr('تحتاج مراجعة', 'Unhealthy')}
                </Badge>
                <Badge tone={health.wal_enabled ? 'green' : 'amber'}>journal_mode={health.journal_mode}</Badge>
                <Badge tone={health.foreign_keys_enabled ? 'green' : 'red'}>
                  FK {health.foreign_keys_enabled ? 'ON' : 'OFF'}
                </Badge>
                <Badge tone="slate">{health.tables_count} {tr('جدول', 'tables')}</Badge>
              </div>
              <p className="text-slate-400">
                integrity_check: <span className="font-mono text-slate-300">{health.integrity_check.join(', ')}</span>
              </p>
              <p className="text-slate-400">
                foreign_key_check:{' '}
                <span className="font-mono text-slate-300">
                  {health.foreign_key_violations.length === 0
                    ? tr('لا مخالفات ✓', 'no violations ✓')
                    : JSON.stringify(health.foreign_key_violations)}
                </span>
              </p>
              <p className="text-slate-400">
                {tr('جداول مفقودة:', 'Missing tables:')}{' '}
                <span className="font-mono text-slate-300">
                  {health.missing_tables.length === 0 ? tr('لا شيء ✓', 'none ✓') : health.missing_tables.join(', ')}
                </span>
              </p>
            </div>
          )}
        </Card>
      </div>

      {/* Users */}
      <Card
        title={tr('إدارة المستخدمين', 'User management')}
        subtitle={isAdmin ? undefined : tr('متاح للمشرف فقط.', 'Admin only.')}
        actions={
          isAdmin ? (
            <Button size="sm" icon={<UserPlus className="h-3.5 w-3.5" />} onClick={() => setUserModal(true)}>
              {tr('إضافة مستخدم', 'Add user')}
            </Button>
          ) : undefined
        }
      >
        {!isAdmin ? (
          <EmptyState title={tr('غير مصرّح', 'Not permitted')} subtitle={tr('تحتاج صلاحية Admin لعرض المستخدمين.', 'Admin role required to list users.')} />
        ) : users.length === 0 ? (
          <EmptyState title={tr('لا يوجد مستخدمون', 'No users')} />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[600px] text-xs">
              <thead>
                <tr className="border-b border-slate-800 text-[11px] uppercase tracking-wide text-slate-500">
                  <th className="px-2 py-2 text-start">{tr('المستخدم', 'User')}</th>
                  <th className="px-2 py-2 text-start">{tr('البريد', 'Email')}</th>
                  <th className="px-2 py-2 text-start">{tr('الصلاحية', 'Role')}</th>
                  <th className="px-2 py-2 text-start">{tr('اللغة', 'Language')}</th>
                  <th className="px-2 py-2 text-start">{tr('آخر دخول', 'Last login')}</th>
                  <th className="px-2 py-2 text-start">{tr('نشط', 'Active')}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {users.map((u) => (
                  <tr key={u.id} className="hover:bg-slate-800/20">
                    <td className="px-2 py-2 font-semibold text-slate-100">{u.username}</td>
                    <td className="px-2 py-2 text-slate-400">{u.email}</td>
                    <td className="px-2 py-2">
                      <Badge tone={u.role === 'admin' ? 'cyan' : 'slate'}>{u.role}</Badge>
                    </td>
                    <td className="px-2 py-2 text-slate-400">{u.preferred_language}</td>
                    <td className="px-2 py-2 text-[11px] text-slate-500">{formatDateTime(u.last_login_at, lang)}</td>
                    <td className="px-2 py-2">
                      <Badge tone={u.is_active ? 'green' : 'red'}>{u.is_active ? 'yes' : 'no'}</Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* Backups */}
      <Card
        title={tr('النسخ الاحتياطي والاستعادة', 'Backup & restore')}
        subtitle={tr(
          'نسخ متسقة عبر sqlite3 Connection.backup مع تحقق SHA-256 قبل الاستعادة.',
          'Consistent snapshots via sqlite3 Connection.backup with SHA-256 verification before restore.'
        )}
        actions={
          isAdmin ? (
            <Button size="sm" variant="secondary" icon={<RefreshCw className="h-3.5 w-3.5" />} onClick={loadBackups}>
              {tr('تحديث القائمة', 'Reload list')}
            </Button>
          ) : undefined
        }
      >
        {!isAdmin ? (
          <EmptyState title={tr('غير مصرّح', 'Not permitted')} subtitle={tr('النسخ الاحتياطي متاح للمشرف فقط.', 'Backups are admin-only.')} />
        ) : (
          <div className="space-y-3">
            <div className="flex flex-wrap items-end gap-2">
              <div className="min-w-[200px] flex-1">
                <Input
                  label={tr('تسمية النسخة (اختياري)', 'Backup label (optional)')}
                  value={backupLabel}
                  onChange={(e) => setBackupLabel(e.target.value)}
                  maxLength={32}
                  placeholder="before_upgrade"
                />
              </div>
              <Button
                loading={creatingBackup}
                icon={<HardDriveDownload className="h-4 w-4" />}
                onClick={async () => {
                  setCreatingBackup(true);
                  try {
                    const meta = await api.createBackup(backupLabel.trim() || undefined);
                    setBackupLabel('');
                    notify(
                      tr(`تم إنشاء نسخة احتياطية: ${meta.filename}`, `Backup created: ${meta.filename}`),
                      'success'
                    );
                    await loadBackups();
                  } catch (err) {
                    notify(err instanceof Error ? err.message : 'Backup failed', 'error');
                  } finally {
                    setCreatingBackup(false);
                  }
                }}
              >
                {tr('إنشاء نسخة الآن', 'Create backup now')}
              </Button>
            </div>

            {backups.length === 0 ? (
              <EmptyState
                title={tr('لا توجد نسخ احتياطية بعد', 'No backups yet')}
                subtitle={tr('أنشئ نسخة قبل أي ترقية أو تغيير إعدادات حرج.', 'Create one before any upgrade or critical change.')}
              />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[700px] text-xs">
                  <thead>
                    <tr className="border-b border-slate-800 text-[11px] uppercase tracking-wide text-slate-500">
                      <th className="px-2 py-2 text-start">{tr('الملف', 'File')}</th>
                      <th className="px-2 py-2 text-start">{tr('الحجم', 'Size')}</th>
                      <th className="px-2 py-2 text-start">{tr('التاريخ', 'Created')}</th>
                      <th className="px-2 py-2 text-start">SHA-256</th>
                      <th className="px-2 py-2 text-end">{tr('إجراءات', 'Actions')}</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60">
                    {backups.map((b) => (
                      <tr key={b.filename} className="hover:bg-slate-800/20">
                        <td className="px-2 py-2 font-mono text-[11px] text-slate-200">{b.filename}</td>
                        <td className="px-2 py-2 text-slate-400">{formatBytes(b.size_bytes)}</td>
                        <td className="px-2 py-2 text-[11px] text-slate-500">{formatDateTime(b.created_at, lang)}</td>
                        <td className="px-2 py-2 font-mono text-[10px] text-slate-500">{b.sha256?.slice(0, 16) || '—'}…</td>
                        <td className="px-2 py-2">
                          <div className="flex items-center justify-end gap-1">
                            <Button size="sm" variant="secondary" icon={<Download className="h-3.5 w-3.5" />} onClick={() => downloadBackup(b.filename)}>
                              {tr('تنزيل', 'Download')}
                            </Button>
                            <Button size="sm" variant="danger" icon={<UploadCloud className="h-3.5 w-3.5" />} onClick={() => setRestoreTarget(b)}>
                              {tr('استعادة', 'Restore')}
                            </Button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            <div className="rounded-lg border border-amber-900/60 bg-amber-950/20 px-3 py-2 text-[11px] leading-relaxed text-amber-300">
              <Database className="mb-0.5 me-1 inline h-3.5 w-3.5" />
              {tr(
                'تُنشأ نسخة أمان تلقائية قبل كل استعادة (إن كان الإعداد مفعّلًا). أوقف Worker وBackend قبل الاستعادة في بيئة الإنتاج لتجنب الجلسات المفتوحة.',
                'A safety snapshot is created before each restore when enabled. In production, stop the worker and API before restoring to avoid open sessions.'
              )}
            </div>
          </div>
        )}
      </Card>

      {/* Create user modal */}
      <Modal
        open={userModal}
        onClose={() => setUserModal(false)}
        title={tr('إضافة مستخدم جديد', 'Add new user')}
        footer={
          <>
            <Button variant="secondary" onClick={() => setUserModal(false)}>
              {tr('إلغاء', 'Cancel')}
            </Button>
            <Button
              loading={creatingUser}
              icon={<Plus className="h-4 w-4" />}
              onClick={async () => {
                setCreatingUser(true);
                try {
                  await api.createUser({
                    username: newUser.username.trim(),
                    email: newUser.email.trim(),
                    password: newUser.password,
                    role: newUser.role,
                    preferred_language: newUser.preferred_language,
                  });
                  notify(tr('تم إنشاء المستخدم', 'User created'), 'success');
                  setUserModal(false);
                  setNewUser({ username: '', email: '', password: '', role: 'operator', preferred_language: lang });
                  await loadUsers();
                } catch (err) {
                  notify(err instanceof Error ? err.message : 'Create failed', 'error');
                } finally {
                  setCreatingUser(false);
                }
              }}
            >
              {tr('إنشاء', 'Create')}
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          <Input
            label={t('username')}
            value={newUser.username}
            onChange={(e) => setNewUser({ ...newUser, username: e.target.value })}
            required
            minLength={2}
          />
          <Input
            label={tr('البريد الإلكتروني', 'Email')}
            type="email"
            value={newUser.email}
            onChange={(e) => setNewUser({ ...newUser, email: e.target.value })}
            required
          />
          <Input
            label={t('password')}
            type="password"
            value={newUser.password}
            onChange={(e) => setNewUser({ ...newUser, password: e.target.value })}
            required
            minLength={8}
          />
          <div className="grid gap-3 sm:grid-cols-2">
            <Select
              label={tr('الصلاحية', 'Role')}
              value={newUser.role}
              onChange={(e) => setNewUser({ ...newUser, role: e.target.value as 'admin' | 'operator' })}
            >
              <option value="operator">{tr('مشغّل', 'Operator')}</option>
              <option value="admin">{tr('مشرف', 'Admin')}</option>
            </Select>
            <Select
              label={tr('اللغة', 'Language')}
              value={newUser.preferred_language}
              onChange={(e) => setNewUser({ ...newUser, preferred_language: e.target.value as 'ar' | 'en' })}
            >
              <option value="ar">العربية</option>
              <option value="en">English</option>
            </Select>
          </div>
        </div>
      </Modal>

      <ConfirmDialog
        open={!!restoreTarget}
        title={tr('استعادة قاعدة البيانات', 'Restore database')}
        message={tr(
          `سيتم استبدال قاعدة البيانات الحالية بالنسخة «${restoreTarget?.filename || ''}». ستُفقد كل التغييرات بعد تاريخ تلك النسخة. هل أنت متأكد؟`,
          `The live database will be replaced by "${restoreTarget?.filename || ''}". All changes made after that snapshot will be lost. Are you sure?`
        )}
        confirmLabel={tr('استعادة الآن', 'Restore now')}
        cancelLabel={tr('إلغاء', 'Cancel')}
        loading={restoring}
        onCancel={() => setRestoreTarget(null)}
        onConfirm={async () => {
          const target = restoreTarget;
          if (!target) return;
          setRestoring(true);
          try {
            const res = await api.restoreBackup(target.filename);
            notify(
              tr(`تمت الاستعادة من ${res.restored_from}`, `Restored from ${res.restored_from}`),
              'success'
            );
            setRestoreTarget(null);
            await Promise.all([loadBackups(), loadHealth(), loadSettings()]);
          } catch (err) {
            notify(err instanceof Error ? err.message : 'Restore failed', 'error');
          } finally {
            setRestoring(false);
          }
        }}
      />
    </div>
  );
};
