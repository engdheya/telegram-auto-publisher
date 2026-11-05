import React, { useCallback, useEffect, useState } from 'react';
import { Braces, RefreshCw, Search } from 'lucide-react';
import { api } from '../services/api';
import type { AuditLog } from '../types';
import { useI18n } from '../contexts/I18nContext';
import { useToast } from '../contexts/ToastContext';
import {
  Badge,
  Button,
  Card,
  EmptyState,
  Modal,
  Pagination,
  Select,
  Spinner,
  formatDateTime,
} from '../components/ui';

const LEVELS = ['', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'];
const CATEGORIES = [
  '',
  'AUTH',
  'SECURITY',
  'TELEGRAM',
  'SOURCE',
  'TARGET',
  'ROUTE',
  'INGESTION',
  'PUBLISHER',
  'QUEUE',
  'BACKUP',
  'SYSTEM',
];

const LEVEL_TONE: Record<string, 'green' | 'red' | 'amber' | 'blue' | 'slate'> = {
  INFO: 'blue',
  WARNING: 'amber',
  ERROR: 'red',
  CRITICAL: 'red',
};

export const LogsPage: React.FC = () => {
  const { t, tr, lang } = useI18n();
  const { notify } = useToast();
  const [items, setItems] = useState<AuditLog[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(30);
  const [level, setLevel] = useState('');
  const [category, setCategory] = useState('');
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<AuditLog | null>(null);

  const load = useCallback(
    async (silent = false) => {
      try {
        const res = await api.listLogs({
          page,
          page_size: pageSize,
          level: level || undefined,
          category: category || undefined,
          search: search.trim() || undefined,
        });
        setItems(res.items);
        setTotal(res.total);
      } catch (err) {
        if (!silent) notify(err instanceof Error ? err.message : 'Failed to load logs', 'error');
      } finally {
        setLoading(false);
      }
    },
    [page, pageSize, level, category, search, notify]
  );

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="space-y-5" data-testid="logs-page">
      <div>
        <h1 className="text-xl font-bold text-slate-50">{tr('السجلات والعمليات', 'Audit & Error Logs')}</h1>
        <p className="mt-0.5 text-xs text-slate-500">
          {tr(
            'أخطاء النظام، أحداث الاتصال، عمليات المستخدمين، وقرارات محرك النشر — مع تصفية وبحث كامل.',
            'System errors, connection events, user operations and publishing decisions — fully searchable and filterable.'
          )}
        </p>
      </div>

      <Card title={tr('تصفية', 'Filters')}>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Select
            label={tr('المستوى', 'Level')}
            value={level}
            onChange={(e) => {
              setPage(1);
              setLevel(e.target.value);
            }}
          >
            {LEVELS.map((l) => (
              <option key={l} value={l}>
                {l || tr('كل المستويات', 'All levels')}
              </option>
            ))}
          </Select>
          <Select
            label={tr('الفئة', 'Category')}
            value={category}
            onChange={(e) => {
              setPage(1);
              setCategory(e.target.value);
            }}
          >
            {CATEGORIES.map((c) => (
              <option key={c} value={c}>
                {c || tr('كل الفئات', 'All categories')}
              </option>
            ))}
          </Select>
          <label className="block sm:col-span-2">
            <span className="mb-1.5 block text-xs font-medium text-slate-300">{tr('بحث', 'Search')}</span>
            <div className="relative">
              <input
                value={search}
                onChange={(e) => {
                  setPage(1);
                  setSearch(e.target.value);
                }}
                placeholder={tr('ابحث في الرسالة أو النوع أو الفاعل...', 'Search message, action or actor...')}
                className="w-full rounded-lg border border-slate-700 bg-slate-950/70 px-3 py-2 pe-9 text-sm text-slate-100 placeholder:text-slate-500 focus:border-cyan-500 focus:outline-none"
              />
              <Search className="pointer-events-none absolute end-3 top-2.5 h-4 w-4 text-slate-500" />
            </div>
          </label>
        </div>
      </Card>

      <Card
        title={`${total} ${tr('سجل', 'log entries')}`}
        actions={
          <Button size="sm" variant="secondary" icon={<RefreshCw className="h-3.5 w-3.5" />} onClick={() => load(true)}>
            {tr('تحديث', 'Refresh')}
          </Button>
        }
      >
        {loading ? (
          <Spinner />
        ) : items.length === 0 ? (
          <EmptyState title={tr('لا توجد سجلات مطابقة', 'No matching log entries')} />
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[820px] text-xs">
                <thead>
                  <tr className="border-b border-slate-800 text-[11px] uppercase tracking-wide text-slate-500">
                    <th className="px-2 py-2 text-start">{tr('الوقت', 'Time')}</th>
                    <th className="px-2 py-2 text-start">{tr('المستوى', 'Level')}</th>
                    <th className="px-2 py-2 text-start">{tr('الفئة', 'Category')}</th>
                    <th className="px-2 py-2 text-start">{tr('الحدث', 'Action')}</th>
                    <th className="px-2 py-2 text-start">{tr('الرسالة', 'Message')}</th>
                    <th className="px-2 py-2 text-start">{tr('الفاعل', 'Actor')}</th>
                    <th className="px-2 py-2 text-end">{tr('تفاصيل', 'Details')}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60">
                  {items.map((log) => (
                    <tr key={log.id} className="hover:bg-slate-800/20">
                      <td className="whitespace-nowrap px-2 py-2 text-[11px] text-slate-500">
                        {formatDateTime(log.created_at, lang)}
                      </td>
                      <td className="px-2 py-2">
                        <Badge tone={LEVEL_TONE[log.level] || 'slate'}>{log.level}</Badge>
                      </td>
                      <td className="px-2 py-2">
                        <Badge tone="slate">{log.category}</Badge>
                      </td>
                      <td className="px-2 py-2 font-mono text-[11px] text-cyan-300">{log.action}</td>
                      <td className="max-w-[420px] px-2 py-2 text-[11px] text-slate-300">{log.message}</td>
                      <td className="px-2 py-2 text-[11px] text-slate-400">{log.actor_username || 'system'}</td>
                      <td className="px-2 py-2 text-end">
                        <Button size="sm" variant="ghost" icon={<Braces className="h-3.5 w-3.5" />} onClick={() => setSelected(log)}>
                          JSON
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pagination
              page={page}
              pageSize={pageSize}
              total={total}
              onChange={setPage}
              labels={{ prev: tr('السابق', 'Prev'), next: tr('التالي', 'Next'), showing: tr('عرض', 'Showing') }}
            />
          </>
        )}
      </Card>

      <Modal
        open={!!selected}
        onClose={() => setSelected(null)}
        wide
        title={`${tr('تفاصيل السجل', 'Log details')} #${selected?.id ?? ''}`}
        footer={
          <Button variant="secondary" onClick={() => setSelected(null)}>
            {tr('إغلاق', 'Close')}
          </Button>
        }
      >
        {selected && (
          <div className="space-y-2">
            <div className="flex flex-wrap gap-1.5">
              <Badge tone={LEVEL_TONE[selected.level] || 'slate'}>{selected.level}</Badge>
              <Badge tone="slate">{selected.category}</Badge>
              <Badge tone="cyan">{selected.action}</Badge>
              {selected.entity_type && (
                <Badge tone="blue">
                  {selected.entity_type}#{selected.entity_id}
                </Badge>
              )}
            </div>
            <p className="text-xs text-slate-300">{selected.message}</p>
            <pre className="max-h-80 overflow-auto rounded-lg border border-slate-800 bg-slate-950/80 p-3 text-[11px] leading-relaxed text-cyan-200">
              {JSON.stringify(
                {
                  id: selected.id,
                  level: selected.level,
                  category: selected.category,
                  action: selected.action,
                  actor_username: selected.actor_username,
                  entity_type: selected.entity_type,
                  entity_id: selected.entity_id,
                  ip_address: selected.ip_address,
                  created_at: selected.created_at,
                  details: selected.details,
                },
                null,
                2
              )}
            </pre>
          </div>
        )}
      </Modal>
    </div>
  );
};
