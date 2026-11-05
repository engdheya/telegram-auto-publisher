import React, { useCallback, useEffect, useState } from 'react';
import {
  AlertTriangle,
  Ban,
  ChevronDown,
  ChevronRight,
  ClipboardCheck,
  RotateCcw,
  RefreshCw,
} from 'lucide-react';
import { api } from '../services/api';
import type { PublishJobDetail } from '../types';
import { useI18n } from '../contexts/I18nContext';
import { useToast } from '../contexts/ToastContext';
import { usePolling } from '../hooks/usePolling';
import {
  Badge,
  Button,
  Card,
  ConfirmDialog,
  EmptyState,
  Pagination,
  Spinner,
  StatusBadge,
  formatDateTime,
} from '../components/ui';

type TabKey = 'ALL' | 'QUEUED' | 'PROCESSING' | 'RETRY_WAIT' | 'FAILED' | 'UNKNOWN' | 'SKIPPED' | 'PUBLISHED';

const TABS: { key: TabKey; ar: string; en: string }[] = [
  { key: 'ALL', ar: 'الكل', en: 'All' },
  { key: 'QUEUED', ar: 'منتظرة', en: 'Queued' },
  { key: 'PROCESSING', ar: 'قيد التنفيذ', en: 'Processing' },
  { key: 'RETRY_WAIT', ar: 'انتظار إعادة', en: 'Retry wait' },
  { key: 'FAILED', ar: 'فاشلة', en: 'Failed' },
  { key: 'UNKNOWN', ar: 'تحتاج مراجعة', en: 'Needs review' },
  { key: 'SKIPPED', ar: 'متخطاة', en: 'Skipped' },
  { key: 'PUBLISHED', ar: 'ناجحة', en: 'Published' },
];

export const QueuePage: React.FC = () => {
  const { tr, lang } = useI18n();
  const { notify } = useToast();
  const [tab, setTab] = useState<TabKey>('ALL');
  const [jobs, setJobs] = useState<PublishJobDetail[]>([]);
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(25);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<number | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [cancelJob, setCancelJob] = useState<PublishJobDetail | null>(null);
  const [reconcileJob, setReconcileJob] = useState<PublishJobDetail | null>(null);

  const load = useCallback(
    async (silent = false) => {
      try {
        const res = await api.listQueueJobs({
          page,
          page_size: pageSize,
          status: tab === 'ALL' ? undefined : tab,
        });
        setJobs(res.items);
        setTotal(res.total);
        setCounts(res.counts_by_status);
      } catch (err) {
        if (!silent) notify(err instanceof Error ? err.message : 'Failed to load queue', 'error');
      } finally {
        setLoading(false);
      }
    },
    [page, pageSize, tab, notify]
  );

  useEffect(() => {
    void load();
  }, [load]);
  usePolling(() => load(true), 10000);

  const act = async (label: string, key: string, fn: () => Promise<{ detail: string }>) => {
    setBusy(key);
    try {
      const res = await fn();
      notify(res.detail || label, 'success');
      await load(true);
    } catch (err) {
      notify(err instanceof Error ? err.message : 'Action failed', 'error');
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="space-y-5" data-testid="queue-page">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-slate-50">{tr('إدارة الطابور', 'Queue Management')}</h1>
          <p className="mt-0.5 text-xs text-slate-500">
            {tr(
              'طابور دائم في SQLite. المهام في حالة UNKNOWN تتطلب مصالحة مع تيليجرام قبل أي إعادة محاولة.',
              'Persistent SQLite queue. UNKNOWN jobs require reconciliation with Telegram before any retry.'
            )}
          </p>
        </div>
        <Button size="sm" variant="secondary" icon={<RefreshCw className="h-3.5 w-3.5" />} onClick={() => load(true)}>
          {tr('تحديث', 'Refresh')}
        </Button>
      </div>

      <div className="flex flex-wrap gap-1.5">
        {TABS.map((t) => {
          const active = tab === t.key;
          const count = t.key === 'ALL' ? Object.values(counts).reduce((a, b) => a + b, 0) : counts[t.key] ?? 0;
          return (
            <button
              key={t.key}
              type="button"
              onClick={() => {
                setPage(1);
                setTab(t.key);
              }}
              className={`rounded-lg border px-2.5 py-1.5 text-[11px] font-medium transition-colors ${
                active
                  ? 'border-cyan-600/60 bg-cyan-500/15 text-cyan-300'
                  : 'border-slate-800 bg-slate-900/60 text-slate-400 hover:text-slate-200'
              }`}
            >
              {tr(t.ar, t.en)}
              <span className="ms-1.5 rounded bg-slate-800/80 px-1 tabular-nums text-[10px] text-slate-400">{count}</span>
            </button>
          );
        })}
      </div>

      <Card title={`${total} ${tr('مهمة', 'jobs')}`}>
        {loading ? (
          <Spinner />
        ) : jobs.length === 0 ? (
          <EmptyState
            title={tr('لا توجد مهام في هذه الحالة', 'No jobs in this state')}
            subtitle={tr(
              'تنشأ المهام تلقائيًا عند وصول منشور جديد ومطابقته لمسار نشر نشط.',
              'Jobs are created automatically when a new post matches an active publishing route.'
            )}
          />
        ) : (
          <div className="space-y-2">
            {jobs.map((j) => {
              const isOpen = expanded === j.id;
              return (
                <div key={j.id} className="rounded-xl border border-slate-800 bg-slate-950/40">
                  <div className="flex flex-wrap items-center gap-2 px-3 py-2.5">
                    <button
                      type="button"
                      onClick={() => setExpanded(isOpen ? null : j.id)}
                      className="flex min-w-0 flex-1 items-center gap-2 text-start"
                    >
                      {isOpen ? <ChevronDown className="h-4 w-4 text-slate-500" /> : <ChevronRight className="h-4 w-4 text-slate-500 rtl:rotate-180" />}
                      <StatusBadge status={j.status} />
                      <span className="font-mono text-[11px] text-slate-400">#{j.id}</span>
                      <span className="min-w-0 truncate text-[11px] text-slate-300">
                        {j.source_title} → {j.target_title}
                      </span>
                      <span className="hidden truncate text-[10px] text-slate-500 sm:block">{j.route_name}</span>
                    </button>

                    <div className="flex flex-wrap items-center gap-1">
                      <Badge tone="slate">
                        {j.attempts_count}/{j.max_attempts}
                      </Badge>
                      {j.content_type && <Badge tone="blue">{j.content_type}</Badge>}
                      {j.album_item_count > 1 && <Badge tone="cyan">album ×{j.album_item_count}</Badge>}
                      {j.next_retry_at && (
                        <Badge tone="amber">
                          {tr('إعادة عند', 'retry at')} {formatDateTime(j.next_retry_at, lang)}
                        </Badge>
                      )}
                      {(j.status === 'FAILED' || j.status === 'SKIPPED' || j.status === 'RETRY_WAIT') && (
                        <Button
                          size="sm"
                          variant="secondary"
                          loading={busy === `retry-${j.id}`}
                          icon={<RotateCcw className="h-3 w-3" />}
                          onClick={() =>
                            act(tr('تمت إعادة المحاولة', 'Job re-queued'), `retry-${j.id}`, () => api.retryQueueJob(j.id))
                          }
                        >
                          {tr('إعادة محاولة', 'Retry')}
                        </Button>
                      )}
                      {j.status === 'UNKNOWN' && (
                        <Button
                          size="sm"
                          variant="success"
                          icon={<ClipboardCheck className="h-3 w-3" />}
                          onClick={() => setReconcileJob(j)}
                        >
                          {tr('مصالحة', 'Reconcile')}
                        </Button>
                      )}
                      {j.status !== 'PUBLISHED' && j.status !== 'PROCESSING' && (
                        <Button
                          size="sm"
                          variant="danger"
                          icon={<Ban className="h-3 w-3" />}
                          onClick={() => setCancelJob(j)}
                        >
                          {tr('إلغاء', 'Cancel')}
                        </Button>
                      )}
                    </div>
                  </div>

                  {isOpen && (
                    <div className="space-y-2.5 border-t border-slate-800 px-3 py-3 text-[11px]">
                      <div className="grid gap-1.5 sm:grid-cols-2">
                        <p className="text-slate-500">
                          {tr('المصدر', 'Source')}: <span className="text-slate-300">{j.source_title}</span>
                        </p>
                        <p className="text-slate-500">
                          {tr('الوجهة', 'Target')}: <span className="text-slate-300">{j.target_title}</span>
                        </p>
                        <p className="text-slate-500">
                          {tr('أُنشئت', 'Created')}: <span className="text-slate-300">{formatDateTime(j.created_at, lang)}</span>
                        </p>
                        <p className="text-slate-500">
                          {tr('آخر تحديث', 'Updated')}: <span className="text-slate-300">{formatDateTime(j.updated_at, lang)}</span>
                        </p>
                        <p className="text-slate-500">
                          {tr('معرف الرسالة في الوجهة', 'Target message IDs')}:{' '}
                          <span className="font-mono text-slate-300">
                            {j.target_message_ids.length > 0 ? j.target_message_ids.join(', ') : j.target_message_id ?? '—'}
                          </span>
                        </p>
                        <p className="text-slate-500">
                          {tr('آخر مصالحة', 'Last reconciliation')}: <span className="text-slate-300">{formatDateTime(j.reconciliation_checked_at, lang)}</span>
                        </p>
                      </div>

                      {j.transformed_text && (
                        <div className="rounded-lg border border-slate-800 bg-slate-900/70 p-2.5">
                          <p className="mb-1 text-[10px] uppercase tracking-wide text-slate-500">
                            {tr('النص بعد التصفية والتوقيع', 'Transformed text')}
                          </p>
                          <p className="whitespace-pre-wrap break-words leading-relaxed text-slate-300">{j.transformed_text}</p>
                        </div>
                      )}

                      {(j.last_error || j.skip_reason || j.unknown_reason) && (
                        <div className="rounded-lg border border-rose-900/50 bg-rose-950/30 p-2.5 text-rose-300">
                          {j.last_error && <p>{tr('خطأ:', 'Error:')} {j.last_error}</p>}
                          {j.skip_reason && <p>{tr('سبب التخطي:', 'Skip reason:')} {j.skip_reason}</p>}
                          {j.unknown_reason && <p>{tr('سبب UNKNOWN:', 'UNKNOWN reason:')} {j.unknown_reason}</p>}
                        </div>
                      )}

                      <div>
                        <p className="mb-1 text-[10px] uppercase tracking-wide text-slate-500">
                          {tr('محاولات النشر', 'Publish attempts')} ({j.attempts.length})
                        </p>
                        {j.attempts.length === 0 ? (
                          <p className="text-slate-500">{tr('لم تُنفَّذ أي محاولة بعد.', 'No attempt executed yet.')}</p>
                        ) : (
                          <div className="space-y-1">
                            {j.attempts.map((a) => (
                              <div
                                key={a.id}
                                className="flex flex-wrap items-center gap-2 rounded-md border border-slate-800 bg-slate-900/60 px-2 py-1"
                              >
                                <Badge tone={a.outcome === 'SUCCESS' ? 'green' : a.outcome === 'IN_FLIGHT' ? 'blue' : a.outcome === 'UNKNOWN' ? 'amber' : 'red'}>
                                  #{a.attempt_number} {a.outcome}
                                </Badge>
                                <span className="text-slate-500">{formatDateTime(a.started_at, lang)}</span>
                                {a.finished_at && <span className="text-slate-600">→ {formatDateTime(a.finished_at, lang)}</span>}
                                <span className="font-mono text-slate-600">{a.worker_id}</span>
                                {a.error_code && <Badge tone="red">{a.error_code}</Badge>}
                                {a.error_message && <span className="w-full truncate text-rose-400">{a.error_message}</span>}
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
            <Pagination
              page={page}
              pageSize={pageSize}
              total={total}
              onChange={setPage}
              labels={{ prev: tr('السابق', 'Prev'), next: tr('التالي', 'Next'), showing: tr('عرض', 'Showing') }}
            />
          </div>
        )}
      </Card>

      <Card title={tr('ملاحظة حول Exactly-Once', 'Exactly-once note')}>
        <p className="text-[11px] leading-relaxed text-slate-400">
          <AlertTriangle className="mb-0.5 me-1 inline h-3.5 w-3.5 text-amber-400" />
          {tr(
            'لا يقدّم تيليجرام ضمانًا مطلقًا للنشر مرة واحدة فقط. عند تعطل العملية أثناء النشر تتحول المهمة إلى UNKNOWN، ويقوم زر المصالحة بالتحقق من الرسائل الأخيرة في الوجهة: إن وُجد المنشور تُعلَّم المهمة PUBLISHED دون إعادة نشر، وإن لم يوجد تُعاد إلى الطابور.',
            'Telegram provides no absolute exactly-once guarantee. If the process dies mid-publish the job becomes UNKNOWN; reconciliation inspects recent target messages — if the post exists the job is marked PUBLISHED without republishing, otherwise it is re-queued.'
          )}
        </p>
      </Card>

      <ConfirmDialog
        open={!!cancelJob}
        title={tr('إلغاء مهمة النشر', 'Cancel publish job')}
        message={tr(
          `سيتم تحويل المهمة #${cancelJob?.id ?? ''} إلى SKIPPED ومنع نشرها. هل تريد المتابعة؟`,
          `Job #${cancelJob?.id ?? ''} will be marked SKIPPED and will not be published. Continue?`
        )}
        confirmLabel={tr('تأكيد الإلغاء', 'Confirm cancel')}
        cancelLabel={tr('رجوع', 'Back')}
        loading={busy === `cancel-${cancelJob?.id}`}
        onCancel={() => setCancelJob(null)}
        onConfirm={async () => {
          const job = cancelJob;
          setCancelJob(null);
          if (job)
            await act(tr('تم إلغاء المهمة', 'Job cancelled'), `cancel-${job.id}`, () => api.cancelQueueJob(job.id));
        }}
      />

      <ConfirmDialog
        open={!!reconcileJob}
        title={tr('مصالحة مهمة UNKNOWN', 'Reconcile UNKNOWN job')}
        message={tr(
          `سيتم فحص آخر رسائل الوجهة «${reconcileJob?.target_title ?? ''}» بحثًا عن المنشور. إن وُجد تُعلَّم المهمة PUBLISHED، وإلا تُعاد للطابور. هل تريد المتابعة؟`,
          `The latest messages of target "${reconcileJob?.target_title ?? ''}" will be scanned. If the post exists the job is marked PUBLISHED, otherwise it is re-queued. Continue?`
        )}
        danger={false}
        confirmLabel={tr('بدء المصالحة', 'Run reconciliation')}
        cancelLabel={tr('رجوع', 'Back')}
        loading={busy === `rec-${reconcileJob?.id}`}
        onCancel={() => setReconcileJob(null)}
        onConfirm={async () => {
          const job = reconcileJob;
          setReconcileJob(null);
          if (job)
            await act(tr('تمت المصالحة', 'Reconciled'), `rec-${job.id}`, () => api.reconcileQueueJob(job.id, true));
        }}
      />
    </div>
  );
};
