import React, { useCallback, useEffect, useState } from 'react';
import {
  CheckCircle2,
  Pencil,
  Plus,
  RefreshCw,
  Send,
  ShieldCheck,
  Target as TargetIcon,
  Trash2,
} from 'lucide-react';
import { api } from '../services/api';
import type { TargetChannel } from '../types';
import { useI18n } from '../contexts/I18nContext';
import { useToast } from '../contexts/ToastContext';
import { usePolling } from '../hooks/usePolling';
import {
  Badge,
  Button,
  Card,
  ConfirmDialog,
  EmptyState,
  Input,
  Modal,
  Spinner,
  Textarea,
  Toggle,
  formatDateTime,
} from '../components/ui';

const emptyForm = { title: '', identifier: '', invite_link: '', is_enabled: true };

export const TargetsPage: React.FC = () => {
  const { tr, lang } = useI18n();
  const { notify } = useToast();
  const [items, setItems] = useState<TargetChannel[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<TargetChannel | null>(null);
  const [form, setForm] = useState(emptyForm);
  const [saving, setSaving] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<TargetChannel | null>(null);
  const [testTarget, setTestTarget] = useState<TargetChannel | null>(null);
  const [testMessage, setTestMessage] = useState('');
  const [testResult, setTestResult] = useState<{ ok: boolean; detail: string } | null>(null);
  const [testing, setTesting] = useState(false);

  const load = useCallback(
    async (silent = false) => {
      try {
        setItems(await api.listTargets());
      } catch (err) {
        if (!silent) notify(err instanceof Error ? err.message : 'Failed to load targets', 'error');
      } finally {
        setLoading(false);
      }
    },
    [notify]
  );

  useEffect(() => {
    void load();
  }, [load]);
  usePolling(() => load(true), 20000);

  const openCreate = () => {
    setEditing(null);
    setForm(emptyForm);
    setModalOpen(true);
  };

  const openEdit = (t: TargetChannel) => {
    setEditing(t);
    setForm({ title: t.title, identifier: t.identifier, invite_link: t.invite_link || '', is_enabled: t.is_enabled });
    setModalOpen(true);
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      const payload = {
        title: form.title.trim(),
        identifier: form.identifier.trim(),
        invite_link: form.invite_link.trim() || null,
        is_enabled: form.is_enabled,
      };
      if (editing) {
        await api.updateTarget(editing.id, payload);
        notify(tr('تم تحديث قناة الوجهة', 'Target updated'), 'success');
      } else {
        await api.createTarget(payload);
        notify(tr('تمت إضافة قناة الوجهة', 'Target created'), 'success');
      }
      setModalOpen(false);
      await load(true);
    } catch (err) {
      notify(err instanceof Error ? err.message : 'Save failed', 'error');
    } finally {
      setSaving(false);
    }
  };

  const action = async (id: number, label: string, fn: () => Promise<unknown>) => {
    setBusyId(id);
    try {
      await fn();
      notify(label, 'success');
      await load(true);
    } catch (err) {
      notify(err instanceof Error ? err.message : 'Action failed', 'error');
    } finally {
      setBusyId(null);
    }
  };

  if (loading) return <Spinner label={tr('جاري تحميل الوجهات...', 'Loading targets...')} />;

  return (
    <div className="space-y-5" data-testid="targets-page">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-slate-50">{tr('قنوات الوجهة', 'Target Channels')}</h1>
          <p className="mt-0.5 text-xs text-slate-500">
            {tr(
              'التحقق من صلاحيات النشر (can_post_messages) وإرسال منشور تجريبي يعرض سبب الفشل الفعلي عند وجود مشكلة.',
              'Verify posting permissions (can_post_messages) and send a test post that surfaces the real failure reason.'
            )}
          </p>
        </div>
        <Button icon={<Plus className="h-4 w-4" />} onClick={openCreate}>
          {tr('إضافة وجهة', 'Add target')}
        </Button>
      </div>

      <Card
        title={`${items.length} ${tr('قناة وجهة', 'target channels')}`}
        actions={
          <Button size="sm" variant="secondary" icon={<RefreshCw className="h-3.5 w-3.5" />} onClick={() => load(true)}>
            {tr('تحديث', 'Refresh')}
          </Button>
        }
      >
        {items.length === 0 ? (
          <EmptyState
            title={tr('لا توجد قنوات وجهة بعد', 'No target channels yet')}
            subtitle={tr(
              'أضف قناة وجهة وتأكد أن الحساب المربوط يملك صلاحية نشر الرسائل فيها.',
              'Add a target channel and make sure the linked account has permission to post in it.'
            )}
            action={<Button icon={<Plus className="h-4 w-4" />} onClick={openCreate}>{tr('إضافة وجهة', 'Add target')}</Button>}
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[900px] text-start text-xs">
              <thead>
                <tr className="border-b border-slate-800 text-[11px] uppercase tracking-wide text-slate-500">
                  <th className="px-2 py-2 text-start">{tr('القناة', 'Channel')}</th>
                  <th className="px-2 py-2 text-start">{tr('المعرّف', 'Identifier')}</th>
                  <th className="px-2 py-2 text-start">{tr('الصلاحيات', 'Permissions')}</th>
                  <th className="px-2 py-2 text-start">{tr('آخر تحقق', 'Last verified')}</th>
                  <th className="px-2 py-2 text-start">{tr('تفعيل', 'Enabled')}</th>
                  <th className="px-2 py-2 text-end">{tr('إجراءات', 'Actions')}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {items.map((t) => (
                  <tr key={t.id} className="align-top hover:bg-slate-800/20">
                    <td className="px-2 py-2.5">
                      <p className="font-semibold text-slate-100">{t.title}</p>
                      {t.last_error && <p className="mt-1 text-[10px] text-rose-400">{t.last_error}</p>}
                      {t.last_test_post_at && (
                        <p className="mt-1 text-[10px] text-slate-500">
                          {tr('اختبار النشر:', 'Test post:')} {formatDateTime(t.last_test_post_at, lang)}
                        </p>
                      )}
                    </td>
                    <td className="px-2 py-2.5 font-mono text-[11px] text-slate-400">
                      {t.username ? `@${t.username}` : t.identifier}
                      {t.telegram_peer_id ? <div className="text-slate-600">{t.telegram_peer_id}</div> : null}
                    </td>
                    <td className="px-2 py-2.5">
                      <div className="flex flex-wrap gap-1">
                        <Badge
                          tone={
                            t.permission_status === 'VERIFIED'
                              ? 'green'
                              : t.permission_status === 'UNVERIFIED'
                              ? 'slate'
                              : 'red'
                          }
                        >
                          {t.permission_status}
                        </Badge>
                        {t.can_post_messages && <Badge tone="cyan">post</Badge>}
                        {t.can_post_media && <Badge tone="blue">media</Badge>}
                      </div>
                    </td>
                    <td className="px-2 py-2.5 text-[11px] text-slate-400">{formatDateTime(t.last_verified_at, lang)}</td>
                    <td className="px-2 py-2.5">
                      <Toggle
                        checked={t.is_enabled}
                        onChange={(next) =>
                          action(t.id, tr('تم تحديث حالة الوجهة', 'Target toggled'), () =>
                            api.updateTarget(t.id, { is_enabled: next })
                          )
                        }
                      />
                    </td>
                    <td className="px-2 py-2.5">
                      <div className="flex flex-wrap items-center justify-end gap-1">
                        <Button
                          size="sm"
                          variant="secondary"
                          loading={busyId === t.id}
                          icon={<ShieldCheck className="h-3.5 w-3.5" />}
                          onClick={() =>
                            action(t.id, tr('تم التحقق من الصلاحيات', 'Permissions verified'), async () => {
                              const res = await api.verifyTarget(t.id);
                              if (!res.ok) throw new Error(res.detail);
                              return res;
                            })
                          }
                        >
                          {tr('تحقق', 'Verify')}
                        </Button>
                        <Button
                          size="sm"
                          variant="success"
                          icon={<Send className="h-3.5 w-3.5" />}
                          onClick={() => {
                            setTestTarget(t);
                            setTestResult(null);
                            setTestMessage(
                              tr(
                                `اختبار نشر من Telegram Auto Publisher — ${t.title}`,
                                `Test post from Telegram Auto Publisher — ${t.title}`
                              )
                            );
                          }}
                        >
                          {tr('اختبار النشر', 'Test post')}
                        </Button>
                        <Button size="sm" variant="ghost" icon={<Pencil className="h-3.5 w-3.5" />} onClick={() => openEdit(t)}>
                          {tr('تعديل', 'Edit')}
                        </Button>
                        <Button size="sm" variant="danger" icon={<Trash2 className="h-3.5 w-3.5" />} onClick={() => setDeleteTarget(t)}>
                          {tr('حذف', 'Delete')}
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Modal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        title={editing ? tr('تعديل قناة وجهة', 'Edit target channel') : tr('إضافة قناة وجهة', 'Add target channel')}
        footer={
          <>
            <Button variant="secondary" onClick={() => setModalOpen(false)}>
              {tr('إلغاء', 'Cancel')}
            </Button>
            <Button form="target-form" type="submit" loading={saving} icon={<TargetIcon className="h-4 w-4" />}>
              {tr('حفظ', 'Save')}
            </Button>
          </>
        }
      >
        <form id="target-form" onSubmit={submit} className="space-y-3">
          <Input
            label={tr('اسم القناة', 'Channel title')}
            value={form.title}
            onChange={(e) => setForm({ ...form, title: e.target.value })}
            required
            maxLength={200}
          />
          <Input
            label={tr('المعرّف', 'Identifier')}
            value={form.identifier}
            onChange={(e) => setForm({ ...form, identifier: e.target.value })}
            required
            placeholder="@my_target_channel"
            hint={tr('يمكن استخدام @username أو الرابط أو المعرف الرقمي.', 'Use @username, t.me link, or numeric peer ID.')}
          />
          <Input
            label={tr('رابط الدعوة (اختياري)', 'Invite link (optional)')}
            value={form.invite_link}
            onChange={(e) => setForm({ ...form, invite_link: e.target.value })}
            placeholder="https://t.me/+abc123"
          />
          <div className="flex items-center gap-2">
            <Toggle checked={form.is_enabled} onChange={(next) => setForm({ ...form, is_enabled: next })} />
            <span className="text-xs text-slate-300">{tr('مفعّل', 'Enabled')}</span>
          </div>
        </form>
      </Modal>

      <Modal
        open={!!testTarget}
        onClose={() => setTestTarget(null)}
        title={tr('اختبار النشر في الوجهة', 'Test publishing to target')}
        footer={
          <>
            <Button variant="secondary" onClick={() => setTestTarget(null)}>
              {tr('إغلاق', 'Close')}
            </Button>
            <Button
              loading={testing}
              icon={<Send className="h-4 w-4" />}
              onClick={async () => {
                if (!testTarget) return;
                setTesting(true);
                setTestResult(null);
                try {
                  const res = await api.testPublishTarget(testTarget.id, testMessage);
                  setTestResult({ ok: res.ok, detail: res.detail });
                  notify(
                    res.ok ? tr('تم إرسال المنشور التجريبي', 'Test post sent') : res.detail,
                    res.ok ? 'success' : 'error'
                  );
                  await load(true);
                } catch (err) {
                  const msg = err instanceof Error ? err.message : 'Failed';
                  setTestResult({ ok: false, detail: msg });
                  notify(msg, 'error');
                } finally {
                  setTesting(false);
                }
              }}
            >
              {tr('إرسال المنشور التجريبي', 'Send test post')}
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          <p className="text-xs text-slate-400">
            {tr('سيتم إرسال رسالة حقيقية إلى', 'A real message will be sent to')}{' '}
            <span className="font-semibold text-slate-200">{testTarget?.title}</span>
          </p>
          <Textarea
            label={tr('نص الاختبار', 'Test message')}
            value={testMessage}
            onChange={(e) => setTestMessage(e.target.value)}
            rows={3}
            maxLength={1000}
          />
          {testResult && (
            <div
              className={`rounded-lg border px-3 py-2 text-xs ${
                testResult.ok
                  ? 'border-emerald-800/60 bg-emerald-950/40 text-emerald-300'
                  : 'border-rose-800/60 bg-rose-950/40 text-rose-300'
              }`}
            >
              <CheckCircle2 className="mb-1 inline h-3.5 w-3.5" /> {testResult.detail}
            </div>
          )}
        </div>
      </Modal>

      <ConfirmDialog
        open={!!deleteTarget}
        title={tr('حذف قناة الوجهة', 'Delete target channel')}
        message={tr(
          `سيتم حذف «${deleteTarget?.title || ''}» وكل المسارات المرتبطة بها. هل تريد المتابعة؟`,
          `"${deleteTarget?.title || ''}" and all routes pointing to it will be deleted. Continue?`
        )}
        confirmLabel={tr('حذف نهائي', 'Delete')}
        cancelLabel={tr('إلغاء', 'Cancel')}
        onCancel={() => setDeleteTarget(null)}
        onConfirm={async () => {
          const target = deleteTarget;
          setDeleteTarget(null);
          if (target) await action(target.id, tr('تم حذف الوجهة', 'Target deleted'), () => api.deleteTarget(target.id));
        }}
      />
    </div>
  );
};
