import React, { useCallback, useEffect, useState } from 'react';
import {
  ChevronDown,
  ChevronRight,
  FileAudio,
  FileText,
  Film,
  Image as ImageIcon,
  Layers,
  Mic,
  RefreshCw,
  RotateCcw,
  Search,
  ShieldAlert,
  Type,
} from 'lucide-react';
import { api } from '../services/api';
import type { MessageEventItem, SourceChannel } from '../types';
import { useI18n } from '../contexts/I18nContext';
import { useToast } from '../contexts/ToastContext';
import {
  Badge,
  Button,
  Card,
  EmptyState,
  Pagination,
  Select,
  Spinner,
  StatusBadge,
  formatBytes,
  formatDateTime,
} from '../components/ui';

const CONTENT_ICONS: Record<string, React.ReactNode> = {
  text: <Type className="h-3.5 w-3.5" />,
  photo: <ImageIcon className="h-3.5 w-3.5" />,
  video: <Film className="h-3.5 w-3.5" />,
  document: <FileText className="h-3.5 w-3.5" />,
  audio: <FileAudio className="h-3.5 w-3.5" />,
  voice: <Mic className="h-3.5 w-3.5" />,
  album: <Layers className="h-3.5 w-3.5" />,
};

export const MessagesPage: React.FC = () => {
  const { tr, lang } = useI18n();
  const { notify } = useToast();
  const [items, setItems] = useState<MessageEventItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(20);
  const [sources, setSources] = useState<SourceChannel[]>([]);
  const [sourceId, setSourceId] = useState('');
  const [contentType, setContentType] = useState('');
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<number | null>(null);
  const [retrying, setRetrying] = useState<number | null>(null);

  const load = useCallback(
    async (silent = false) => {
      try {
        const res = await api.listMessages({
          page,
          page_size: pageSize,
          source_id: sourceId ? Number(sourceId) : undefined,
          content_type: contentType || undefined,
          search: search.trim() || undefined,
        });
        setItems(res.items);
        setTotal(res.total);
      } catch (err) {
        if (!silent) notify(err instanceof Error ? err.message : 'Failed to load messages', 'error');
      } finally {
        setLoading(false);
      }
    },
    [page, pageSize, sourceId, contentType, search, notify]
  );

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    api.listSources().then(setSources).catch(() => undefined);
  }, []);

  const retry = async (jobId: number) => {
    setRetrying(jobId);
    try {
      const res = await api.retryQueueJob(jobId);
      notify(res.detail, 'success');
      await load(true);
    } catch (err) {
      notify(err instanceof Error ? err.message : 'Retry failed', 'error');
    } finally {
      setRetrying(null);
    }
  };

  // SKIPPED is frequently caused by Telegram content protection / permissions — a manual
  // retry would be pointless there, so only genuinely retryable states expose the button.
  const canRetry = (status: string) => status === 'FAILED' || status === 'RETRY_WAIT';

  return (
    <div className="space-y-5" data-testid="messages-page">
      <div>
        <h1 className="text-xl font-bold text-slate-50">{tr('سجل المنشورات والنشر', 'Publishing History')}</h1>
        <p className="mt-0.5 text-xs text-slate-500">
          {tr(
            'كل حدث مستلم من المصادر مع مهام النشر المستقلة لكل وجهة وحالتها وسبب الفشل.',
            'Every received source event with its independent per-target publish jobs, status and failure reason.'
          )}
        </p>
      </div>

      <Card title={tr('تصفية السجل', 'Filter history')}>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Select
            label={tr('المصدر', 'Source')}
            value={sourceId}
            onChange={(e) => {
              setPage(1);
              setSourceId(e.target.value);
            }}
          >
            <option value="">{tr('كل المصادر', 'All sources')}</option>
            {sources.map((s) => (
              <option key={s.id} value={s.id}>
                {s.title}
              </option>
            ))}
          </Select>
          <Select
            label={tr('نوع المحتوى', 'Content type')}
            value={contentType}
            onChange={(e) => {
              setPage(1);
              setContentType(e.target.value);
            }}
          >
            <option value="">{tr('كل الأنواع', 'All types')}</option>
            {Object.keys(CONTENT_ICONS).map((k) => (
              <option key={k} value={k}>
                {k}
              </option>
            ))}
          </Select>
          <label className="block sm:col-span-2">
            <span className="mb-1.5 block text-xs font-medium text-slate-300">{tr('بحث في النص', 'Search text')}</span>
            <div className="relative">
              <input
                value={search}
                onChange={(e) => {
                  setPage(1);
                  setSearch(e.target.value);
                }}
                placeholder={tr('ابحث داخل نص المنشورات...', 'Search inside post text...')}
                className="w-full rounded-lg border border-slate-700 bg-slate-950/70 px-3 py-2 pe-9 text-sm text-slate-100 placeholder:text-slate-500 focus:border-cyan-500 focus:outline-none"
              />
              <Search className="pointer-events-none absolute end-3 top-2.5 h-4 w-4 text-slate-500" />
            </div>
          </label>
        </div>
      </Card>

      <Card
        title={`${total} ${tr('منشور مستلم', 'received posts')}`}
        actions={
          <Button size="sm" variant="secondary" icon={<RefreshCw className="h-3.5 w-3.5" />} onClick={() => load(true)}>
            {tr('تحديث', 'Refresh')}
          </Button>
        }
      >
        {loading ? (
          <Spinner />
        ) : items.length === 0 ? (
          <EmptyState
            title={tr('لا توجد منشورات مستلمة', 'No received posts')}
            subtitle={tr(
              'ستظهر المنشورات هنا فور وصول منشور جديد إلى قناة مصدر مفعّلة ومرتبطة بمسار نشط.',
              'Posts appear here as soon as a new message arrives in an enabled source linked to an active route.'
            )}
          />
        ) : (
          <div className="space-y-2">
            {items.map((ev) => {
              const isOpen = expanded === ev.id;
              return (
                <div key={ev.id} className="rounded-xl border border-slate-800 bg-slate-950/40">
                  <button
                    type="button"
                    onClick={() => setExpanded(isOpen ? null : ev.id)}
                    className="flex w-full flex-wrap items-center gap-2 px-3 py-2.5 text-start"
                  >
                    {isOpen ? <ChevronDown className="h-4 w-4 text-slate-500" /> : <ChevronRight className="h-4 w-4 text-slate-500 rtl:rotate-180" />}
                    <span className="rounded-md bg-slate-800/70 p-1 text-slate-400">
                      {CONTENT_ICONS[ev.content_type] || <Type className="h-3.5 w-3.5" />}
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-xs font-semibold text-slate-100">
                        {ev.raw_text?.slice(0, 110) || tr('(بدون نص / وسائط فقط)', '(no text / media only)')}
                      </p>
                      <p className="truncate text-[11px] text-slate-500">
                        {ev.source_title} · msg #{ev.telegram_message_id}
                        {ev.grouped_id ? ` · album ${ev.grouped_id} (${ev.album_item_count})` : ''} ·{' '}
                        {formatDateTime(ev.received_at, lang)}
                      </p>
                    </div>
                    <div className="flex flex-wrap items-center gap-1">
                      {ev.is_protected_content && (
                        <Badge tone="amber">
                          <ShieldAlert className="h-3 w-3" /> {tr('محمي', 'protected')}
                        </Badge>
                      )}
                      {ev.jobs.length === 0 ? (
                        <Badge tone="slate">{tr('لا مهام', 'no jobs')}</Badge>
                      ) : (
                        ev.jobs.map((j) => <StatusBadge key={j.id} status={j.status} />)
                      )}
                    </div>
                  </button>

                  {isOpen && (
                    <div className="space-y-3 border-t border-slate-800 px-3 py-3">
                      {ev.is_protected_content && (
                        <div className="rounded-lg border border-amber-800/60 bg-amber-950/30 px-3 py-2 text-[11px] text-amber-300">
                          {tr('محتوى محمي (noforwards):', 'Protected content (noforwards):')} {ev.protection_reason || 'noforwards'}
                        </div>
                      )}

                      {ev.raw_text && (
                        <div className="rounded-lg border border-slate-800 bg-slate-900/70 p-2.5">
                          <p className="mb-1 text-[10px] uppercase tracking-wide text-slate-500">{tr('النص الأصلي', 'Raw text')}</p>
                          <p className="whitespace-pre-wrap break-words text-[11px] leading-relaxed text-slate-300">
                            {ev.raw_text}
                          </p>
                        </div>
                      )}

                      {ev.media_items.length > 0 && (
                        <div>
                          <p className="mb-1 text-[10px] uppercase tracking-wide text-slate-500">
                            {tr('الوسائط', 'Media')} ({ev.media_items.length})
                          </p>
                          <div className="grid gap-1.5 sm:grid-cols-2">
                            {ev.media_items.map((m) => (
                              <div key={m.id} className="rounded-lg border border-slate-800 bg-slate-900/60 px-2.5 py-1.5 text-[11px]">
                                <p className="flex items-center justify-between gap-2 text-slate-300">
                                  <span className="truncate">
                                    #{m.position} {m.media_type} {m.file_name ? `· ${m.file_name}` : ''}
                                  </span>
                                  <Badge tone={m.status === 'READY' ? 'green' : m.status === 'SKIPPED' ? 'amber' : 'slate'}>
                                    {m.status}
                                  </Badge>
                                </p>
                                <p className="truncate text-slate-500">
                                  {m.mime_type || '—'} · {formatBytes(m.file_size)}
                                  {m.duration_seconds ? ` · ${m.duration_seconds}s` : ''}
                                  {m.width && m.height ? ` · ${m.width}×${m.height}` : ''}
                                </p>
                                {m.error_reason && <p className="text-rose-400">{m.error_reason}</p>}
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      <div>
                        <p className="mb-1 text-[10px] uppercase tracking-wide text-slate-500">
                          {tr('مهام النشر للوجهات', 'Per-target publish jobs')} ({ev.jobs.length})
                        </p>
                        {ev.jobs.length === 0 ? (
                          <p className="text-[11px] text-slate-500">
                            {tr('لم يتم إنشاء أي مهمة (لا يوجد مسار مطابق أو تم استبعاده بالقواعد).', 'No jobs created (no matching route or filtered out).')}
                          </p>
                        ) : (
                          <div className="space-y-1.5">
                            {ev.jobs.map((j) => (
                              <div
                                key={j.id}
                                className="flex flex-wrap items-center gap-2 rounded-lg border border-slate-800 bg-slate-900/60 px-2.5 py-1.5 text-[11px]"
                              >
                                <StatusBadge status={j.status} />
                                <span className="font-mono text-slate-400">job #{j.id}</span>
                                <span className="text-slate-500">
                                  {j.route_name} → <span className="text-slate-300">{j.target_title}</span>
                                </span>
                                <span className="text-slate-600">
                                  {j.attempts_count}/{j.max_attempts} {tr('محاولات', 'attempts')}
                                </span>
                                {j.target_message_id && (
                                  <Badge tone="green">target msg #{j.target_message_id}</Badge>
                                )}
                                <span className="ms-auto flex items-center gap-1">
                                  {j.status === 'PUBLISHED' && j.published_at && (
                                    <span className="text-slate-500">{formatDateTime(j.published_at, lang)}</span>
                                  )}
                                  {canRetry(j.status) && (
                                    <Button
                                      size="sm"
                                      variant="secondary"
                                      loading={retrying === j.id}
                                      icon={<RotateCcw className="h-3 w-3" />}
                                      onClick={() => retry(j.id)}
                                    >
                                      {tr('إعادة محاولة', 'Retry')}
                                    </Button>
                                  )}
                                </span>
                                {(j.last_error || j.skip_reason || j.unknown_reason) && (
                                  <p className="w-full text-[11px] text-rose-400">
                                    {j.last_error || j.skip_reason || j.unknown_reason}
                                  </p>
                                )}
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
    </div>
  );
};
