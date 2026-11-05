import React, { useCallback, useEffect, useState } from 'react';
import {
  CheckCircle2,
  Inbox,
  Pause,
  Pencil,
  Play,
  Plus,
  RefreshCw,
  ShieldAlert,
  Trash2,
  Zap,
} from 'lucide-react';
import { api } from '../services/api';
import type { SourceChannel } from '../types';
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
  Toggle,
  formatDateTime,
} from '../components/ui';

const emptyForm = { title: '', identifier: '', invite_link: '', is_enabled: true };

export const SourcesPage: React.FC = () => {
  const { tr, lang } = useI18n();
  const { notify } = useToast();
  const [items, setItems] = useState<SourceChannel[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<SourceChannel | null>(null);
  const [form, setForm] = useState(emptyForm);
  const [saving, setSaving] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<SourceChannel | null>(null);

  const load = useCallback(
    async (silent = false) => {
      try {
        setItems(await api.listSources());
      } catch (err) {
        if (!silent) notify(err instanceof Error ? err.message : 'Failed to load sources', 'error');
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

  const openEdit = (s: SourceChannel) => {
    setEditing(s);
    setForm({
      title: s.title,
      identifier: s.identifier,
      invite_link: s.invite_link || '',
      is_enabled: s.is_enabled,
    });
    setModalOpen(true);
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      if (editing) {
        await api.updateSource(editing.id, {
          title: form.title.trim(),
          identifier: form.identifier.trim(),
          invite_link: form.invite_link.trim() || null,
          is_enabled: form.is_enabled,
        });
        notify(tr('تم تحديث قناة المصدر', 'Source updated'), 'success');
      } else {
        await api.createSource({
          title: form.title.trim(),
          identifier: form.identifier.trim(),
          invite_link: form.invite_link.trim() || null,
          is_enabled: form.is_enabled,
        });
        notify(tr('تمت إضافة قناة المصدر', 'Source created'), 'success');
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

  const statusTone = (s: SourceChannel) => {
    if (!s.is_enabled) return 'slate' as const;
    if (s.monitoring_status === 'ACTIVE') return 'green' as const;
    if (s.monitoring_status === 'ERROR') return 'red' as const;
    if (s.monitoring_status === 'PAUSED') return 'amber' as const;
    return 'blue' as const;
  };

  if (loading) return <Spinner label={tr('جاري تحميل المصادر...', 'Loading sources...')} />;

  return (
    <div className="space-y-5" data-testid="sources-page">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-slate-50">{tr('قنوات المصدر', 'Source Channels')}</h1>
          <p className="mt-0.5 text-xs text-slate-500">
            {tr(
              'تُراقَب المنشورات الجديدة فقط بدءًا من baseline_message_id الموثّق — لا استيراد للأرشيف القديم.',
              'Only new posts are monitored from the recorded baseline_message_id — no archive import.'
            )}
          </p>
        </div>
        <Button icon={<Plus className="h-4 w-4" />} onClick={openCreate}>
          {tr('إضافة مصدر', 'Add source')}
        </Button>
      </div>

      <Card
        title={`${items.length} ${tr('قناة مصدر', 'source channels')}`}
        actions={
          <Button size="sm" variant="secondary" icon={<RefreshCw className="h-3.5 w-3.5" />} onClick={() => load(true)}>
            {tr('تحديث', 'Refresh')}
          </Button>
        }
      >
        {items.length === 0 ? (
          <EmptyState
            title={tr('لا توجد قنوات مصدر بعد', 'No source channels yet')}
            subtitle={tr(
              'أضف قناة عامة مثل @channel_name أو استخدم معرف رقمي، ثم ابدأ المراقبة بعد التحقق من الوصول.',
              'Add a public channel like @channel_name or a numeric ID, then verify access and start monitoring.'
            )}
            action={<Button icon={<Plus className="h-4 w-4" />} onClick={openCreate}>{tr('إضافة مصدر', 'Add source')}</Button>}
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[900px] text-start text-xs">
              <thead>
                <tr className="border-b border-slate-800 text-[11px] uppercase tracking-wide text-slate-500">
                  <th className="px-2 py-2 text-start">{tr('القناة', 'Channel')}</th>
                  <th className="px-2 py-2 text-start">{tr('المعرّف', 'Identifier')}</th>
                  <th className="px-2 py-2 text-start">{tr('الحالة', 'Status')}</th>
                  <th className="px-2 py-2 text-start">baseline / last</th>
                  <th className="px-2 py-2 text-start">{tr('آخر معالجة', 'Last processed')}</th>
                  <th className="px-2 py-2 text-start">{tr('تفعيل', 'Enabled')}</th>
                  <th className="px-2 py-2 text-end">{tr('إجراءات', 'Actions')}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {items.map((s) => (
                  <tr key={s.id} className="align-top hover:bg-slate-800/20">
                    <td className="px-2 py-2.5">
                      <p className="font-semibold text-slate-100">{s.title}</p>
                      <div className="mt-1 flex flex-wrap items-center gap-1">
                        {s.noforwards_protected && (
                          <Badge tone="amber">
                            <ShieldAlert className="h-3 w-3" /> noforwards
                          </Badge>
                        )}
                        {s.last_error && <Badge tone="red">{s.last_error.slice(0, 60)}</Badge>}
                      </div>
                    </td>
                    <td className="px-2 py-2.5 font-mono text-[11px] text-slate-400">
                      {s.username ? `@${s.username}` : s.identifier}
                      {s.telegram_peer_id ? <div className="text-slate-600">{s.telegram_peer_id}</div> : null}
                    </td>
                    <td className="px-2 py-2.5">
                      <Badge tone={statusTone(s)}>{s.monitoring_status}</Badge>
                      {s.access_verified_at && (
                        <p className="mt-1 text-[10px] text-slate-500">
                          {tr('تم التحقق', 'verified')} {formatDateTime(s.access_verified_at, lang)}
                        </p>
                      )}
                    </td>
                    <td className="px-2 py-2.5 font-mono text-[11px] text-slate-400">
                      {s.baseline_message_id ?? '—'} / {s.last_processed_message_id ?? '—'}
                    </td>
                    <td className="px-2 py-2.5 text-[11px] text-slate-400">{formatDateTime(s.last_processed_at, lang)}</td>
                    <td className="px-2 py-2.5">
                      <Toggle
                        checked={s.is_enabled}
                        onChange={(next) =>
                          action(s.id, tr('تم تحديث حالة المصدر', 'Source toggled'), () =>
                            api.updateSource(s.id, { is_enabled: next })
                          )
                        }
                      />
                    </td>
                    <td className="px-2 py-2.5">
                      <div className="flex flex-wrap items-center justify-end gap-1">
                        <Button
                          size="sm"
                          variant="secondary"
                          loading={busyId === s.id}
                          icon={<CheckCircle2 className="h-3.5 w-3.5" />}
                          onClick={() =>
                            action(s.id, tr('تم التحقق من الوصول', 'Access verified'), async () => {
                              const res = await api.verifySource(s.id);
                              if (!res.accessible) throw new Error(res.detail);
                              return res;
                            })
                          }
                        >
                          {tr('اختبار الوصول', 'Verify')}
                        </Button>
                        {s.monitoring_status === 'ACTIVE' ? (
                          <Button
                            size="sm"
                            variant="secondary"
                            icon={<Pause className="h-3.5 w-3.5" />}
                            onClick={() => action(s.id, tr('تم إيقاف المراقبة', 'Monitoring stopped'), () => api.stopSource(s.id))}
                          >
                            {tr('إيقاف', 'Stop')}
                          </Button>
                        ) : (
                          <Button
                            size="sm"
                            variant="success"
                            icon={<Play className="h-3.5 w-3.5" />}
                            onClick={() => action(s.id, tr('بدأت المراقبة', 'Monitoring started'), () => api.startSource(s.id))}
                          >
                            {tr('بدأ المراقبة', 'Start')}
                          </Button>
                        )}
                        <Button size="sm" variant="ghost" icon={<Pencil className="h-3.5 w-3.5" />} onClick={() => openEdit(s)}>
                          {tr('تعديل', 'Edit')}
                        </Button>
                        <Button size="sm" variant="danger" icon={<Trash2 className="h-3.5 w-3.5" />} onClick={() => setDeleteTarget(s)}>
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

      <Card title={tr('كيف تعمل المراقبة؟', 'How monitoring works')}>
        <ul className="space-y-1.5 text-[11px] leading-relaxed text-slate-400">
          <li>• {tr('عند أول تشغيل، يُسجَّل baseline_message_id كأعلى معرف موجود ولا يُنشر أي منشور قديم.', 'On first start the highest message ID is recorded as baseline_message_id and nothing old is published.')}</li>
          <li>• {tr('بعد انقطاع الاتصال، يحاول النظام التقاط الرسائل الفائتة ضمن حدود واجهة تيليجرام.', 'After a disconnect the system attempts to catch up on missed messages within Telegram API limits.')}</li>
          <li>• {tr('التعديلات والحذف لا تُنشر أبدًا؛ ويُحتسب كل حدث مرة واحدة فقط عبر قيد UNIQUE.', 'Edits and deletions are never relayed; each event is counted once via a UNIQUE constraint.')}</li>
          <li>• {tr('المحتوى المحمي (noforwards) يُسجَّل SKIPPED مع سبب واضح ولا يُعاد نشره.', 'Protected (noforwards) content is recorded SKIPPED with a clear reason and never reposted.')}</li>
        </ul>
      </Card>

      <Modal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        title={editing ? tr('تعديل قناة مصدر', 'Edit source channel') : tr('إضافة قناة مصدر', 'Add source channel')}
        footer={
          <>
            <Button variant="secondary" onClick={() => setModalOpen(false)}>
              {tr('إلغاء', 'Cancel')}
            </Button>
            <Button form="source-form" type="submit" loading={saving} icon={<Inbox className="h-4 w-4" />}>
              {tr('حفظ', 'Save')}
            </Button>
          </>
        }
      >
        <form id="source-form" onSubmit={submit} className="space-y-3">
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
            placeholder="@channel_name أو -1001234567890"
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
          {!editing && (
            <div className="rounded-lg border border-cyan-900/60 bg-cyan-950/30 px-3 py-2 text-[11px] text-cyan-300">
              <Zap className="mb-1 inline h-3 w-3" />{' '}
              {tr(
                'سيتم فحص القناة عبر Telethon فور الإنشاء وتسجيل baseline_message_id قبل بدء المراقبة.',
                'The channel is resolved through Telethon on creation and baseline_message_id is recorded before monitoring starts.'
              )}
            </div>
          )}
        </form>
      </Modal>

      <ConfirmDialog
        open={!!deleteTarget}
        title={tr('حذف قناة المصدر', 'Delete source channel')}
        message={tr(
          `سيتم حذف «${deleteTarget?.title || ''}» وكل المسارات المرتبطة به. السجلات التاريخية للمنشورات ستبقى في قاعدة البيانات. هل تريد المتابعة؟`,
          `"${deleteTarget?.title || ''}" and its routes will be deleted. Historical message records remain in the database. Continue?`
        )}
        confirmLabel={tr('حذف نهائي', 'Delete')}
        cancelLabel={tr('إلغاء', 'Cancel')}
        onCancel={() => setDeleteTarget(null)}
        onConfirm={async () => {
          const target = deleteTarget;
          setDeleteTarget(null);
          if (target) await action(target.id, tr('تم حذف المصدر', 'Source deleted'), () => api.deleteSource(target.id));
        }}
      />
    </div>
  );
};
