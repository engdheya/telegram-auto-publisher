import React, { useCallback, useEffect, useState } from 'react';
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Database,
  GitBranch,
  Inbox,
  ListChecks,
  MessageSquare,
  RefreshCw,
  Send,
  Target,
  XCircle,
  ServerCog,
} from 'lucide-react';
import { api } from '../services/api';
import type { DashboardOverview } from '../types';
import { useI18n } from '../contexts/I18nContext';
import { useToast } from '../contexts/ToastContext';
import { usePolling } from '../hooks/usePolling';
import { Badge, Button, Card, EmptyState, Spinner, StatCard, formatDateTime } from '../components/ui';

const LEVEL_TONE: Record<string, 'green' | 'red' | 'amber' | 'blue' | 'slate'> = {
  INFO: 'blue',
  WARNING: 'amber',
  ERROR: 'red',
  CRITICAL: 'red',
};

export const DashboardPage: React.FC = () => {
  const { t, tr, lang } = useI18n();
  const { notify } = useToast();
  const [data, setData] = useState<DashboardOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(
    async (silent = false) => {
      if (!silent) setLoading((prev) => prev && true);
      try {
        const res = await api.getDashboardOverview();
        setData(res);
      } catch (err) {
        if (!silent) notify(err instanceof Error ? err.message : 'Failed to load dashboard', 'error');
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [notify]
  );

  useEffect(() => {
    void load();
  }, [load]);

  usePolling(() => load(true), 15000);

  const onRefresh = () => {
    setRefreshing(true);
    void load(true);
  };

  if (loading && !data) return <Spinner label={tr('جاري تحميل المؤشرات...', 'Loading dashboard metrics...')} />;

  const db = data?.database_health;

  return (
    <div className="space-y-5" data-testid="dashboard-page">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-slate-50">{t('navDashboard')}</h1>
          <p className="mt-0.5 text-xs text-slate-500">
            {tr('نظرة شاملة على حالة النظام والاتصال والطوابير', 'System health, connectivity and queue overview')}
          </p>
        </div>
        <Button variant="secondary" icon={<RefreshCw className={`h-4 w-4 ${refreshing ? 'animate-spin' : ''}`} />} onClick={onRefresh}>
          {t('refresh')}
        </Button>
      </div>

      {/* Connectivity strip */}
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <div className="flex items-center gap-3 rounded-xl border border-slate-800 bg-slate-900/60 px-4 py-3">
          <span className={`rounded-lg p-2 ${data?.telegram_connected ? 'bg-emerald-500/15 text-emerald-300' : 'bg-rose-500/15 text-rose-300'}`}>
            <Send className="h-4 w-4" />
          </span>
          <div className="min-w-0">
            <p className="text-xs font-semibold text-slate-200">
              {data?.telegram_connected ? t('telegramConnected') : t('telegramDisconnected')}
            </p>
            <p className="truncate text-[11px] text-slate-500">
              {data?.telegram_display_name || data?.telegram_username || data?.telegram_auth_state || '—'}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3 rounded-xl border border-slate-800 bg-slate-900/60 px-4 py-3">
          <span className={`rounded-lg p-2 ${data?.worker_alive ? 'bg-emerald-500/15 text-emerald-300' : 'bg-amber-500/15 text-amber-300'}`}>
            <ServerCog className="h-4 w-4" />
          </span>
          <div className="min-w-0">
            <p className="text-xs font-semibold text-slate-200">{data?.worker_alive ? t('workerRunning') : t('workerOffline')}</p>
            <p className="truncate text-[11px] text-slate-500">
              {tr('آخر نبضة:', 'Heartbeat:')} {formatDateTime(data?.worker_last_heartbeat, lang)}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3 rounded-xl border border-slate-800 bg-slate-900/60 px-4 py-3">
          <span className={`rounded-lg p-2 ${db?.healthy ? 'bg-emerald-500/15 text-emerald-300' : 'bg-rose-500/15 text-rose-300'}`}>
            <Database className="h-4 w-4" />
          </span>
          <div className="min-w-0">
            <p className="text-xs font-semibold text-slate-200">
              {db?.healthy ? t('walHealthy') : tr('قاعدة البيانات تحتاج مراجعة', 'Database needs attention')}
            </p>
            <p className="truncate text-[11px] text-slate-500">
              journal_mode={db?.journal_mode ?? '—'} · FK {db?.foreign_keys_enabled ? 'ON' : 'OFF'} · {db?.tables_count ?? 0}{' '}
              {tr('جدول', 'tables')}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3 rounded-xl border border-slate-800 bg-slate-900/60 px-4 py-3">
          <span className="rounded-lg bg-cyan-500/15 p-2 text-cyan-300">
            <Activity className="h-4 w-4" />
          </span>
          <div className="min-w-0">
            <p className="text-xs font-semibold text-slate-200">
              {tr('حالة المصادقة', 'Auth state')}: {data?.telegram_auth_state || '—'}
            </p>
            <p className="truncate text-[11px] text-slate-500">
              {tr('المصادر النشطة', 'Active sources')}: {data?.sources_active ?? 0}/{data?.sources_total ?? 0}
            </p>
          </div>
        </div>
      </div>

      {/* Metrics */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label={t('sourcesCount')} value={data?.sources_total ?? 0} tone="cyan" icon={<Inbox className="h-4 w-4" />} hint={`${data?.sources_active ?? 0} ${tr('نشط', 'active')}`} />
        <StatCard label={t('targetsCount')} value={data?.targets_total ?? 0} tone="indigo" icon={<Target className="h-4 w-4" />} hint={`${data?.targets_verified ?? 0} ${tr('موثّق', 'verified')}`} />
        <StatCard label={t('activeRoutesCount')} value={data?.routes_active ?? 0} tone="emerald" icon={<GitBranch className="h-4 w-4" />} hint={`${data?.routes_total ?? 0} ${tr('إجمالي', 'total')}`} />
        <StatCard testId="stat-received" label={t('receivedPostsCount')} value={data?.messages_received_total ?? 0} tone="slate" icon={<MessageSquare className="h-4 w-4" />} />
        <StatCard testId="stat-published" label={t('publishedCount')} value={data?.jobs_published ?? 0} tone="emerald" icon={<CheckCircle2 className="h-4 w-4" />} />
        <StatCard testId="stat-failed" label={t('failedCount')} value={data?.jobs_failed ?? 0} tone="rose" icon={<XCircle className="h-4 w-4" />} />
        <StatCard
          testId="stat-waiting"
          label={t('waitingCount')}
          value={data?.jobs_waiting ?? 0}
          tone="amber"
          icon={<ListChecks className="h-4 w-4" />}
          hint={`${data?.jobs_processing ?? 0} ${tr('قيد التنفيذ', 'processing')} · ${data?.jobs_skipped ?? 0} ${tr('متخطاة', 'skipped')}`}
        />
        <StatCard
          testId="stat-unknown"
          label={t('unknownCount')}
          value={data?.jobs_unknown ?? 0}
          tone="fuchsia"
          icon={<AlertTriangle className="h-4 w-4" />}
          hint={tr('تتطلب مصالحة قبل الإعادة', 'Reconcile before retrying')}
        />
      </div>

      <Card title={t('recentActivity')} subtitle={tr('أحدث 10 عمليات مسجلة في سجل التدقيق', 'Latest 10 audit log entries')}>
        {!data || data.recent_activities.length === 0 ? (
          <EmptyState title={t('noData')} />
        ) : (
          <ul className="divide-y divide-slate-800/70">
            {data.recent_activities.map((log) => (
              <li key={log.id} className="flex flex-wrap items-start gap-2 py-2.5 first:pt-0 last:pb-0">
                <Badge tone={LEVEL_TONE[log.level] || 'slate'}>{log.level}</Badge>
                <Badge tone="slate">{log.category}</Badge>
                <div className="min-w-0 flex-1">
                  <p className="text-xs text-slate-200">{log.message}</p>
                  <p className="mt-0.5 text-[11px] text-slate-500">
                    {log.action} · {log.actor_username || 'system'} · {formatDateTime(log.created_at, lang)}
                  </p>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
};
