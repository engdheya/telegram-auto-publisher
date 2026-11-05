import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ArrowRight,
  Filter,
  GitBranch,
  Pencil,
  Plus,
  RefreshCw,
  Trash2,
  Wand2,
  Power,
} from 'lucide-react';
import { api } from '../services/api';
import type { ContentType, PublishingRoute, RouteFilterConfig, SourceChannel, TargetChannel } from '../types';
import { useI18n } from '../contexts/I18nContext';
import { useToast } from '../contexts/ToastContext';
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
  Textarea,
  Toggle,
  formatDateTime,
} from '../components/ui';

const ALL_TYPES: ContentType[] = ['text', 'photo', 'video', 'document', 'audio', 'voice', 'album'];

const defaultFilters = (): RouteFilterConfig => ({
  allowed_content_types: [...ALL_TYPES],
  include_keywords: [],
  exclude_keywords: [],
  allowed_extensions: [],
  min_text_length: null,
  max_text_length: null,
  prefix_text: null,
  suffix_text: null,
  target_signature: null,
  strip_urls: false,
});

const csvToArr = (v: string) =>
  v
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean);

export const RoutesPage: React.FC = () => {
  const { tr, lang } = useI18n();
  const { notify } = useToast();
  const [routes, setRoutes] = useState<PublishingRoute[]>([]);
  const [sources, setSources] = useState<SourceChannel[]>([]);
  const [targets, setTargets] = useState<TargetChannel[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<number | null>(null);

  const [createOpen, setCreateOpen] = useState(false);
  const [editing, setEditing] = useState<PublishingRoute | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<PublishingRoute | null>(null);
  const [filterRoute, setFilterRoute] = useState<PublishingRoute | null>(null);

  // single route form
  const [form, setForm] = useState({
    name: '',
    description: '',
    source_channel_id: '',
    target_channel_id: '',
    is_enabled: true,
    priority: 100,
  });
  // bulk builder
  const [bulkMode, setBulkMode] = useState(false);
  const [bulkName, setBulkName] = useState('Route');
  const [bulkSources, setBulkSources] = useState<number[]>([]);
  const [bulkTargets, setBulkTargets] = useState<number[]>([]);
  const [filters, setFilters] = useState<RouteFilterConfig>(defaultFilters());
  const [saving, setSaving] = useState(false);

  const load = useCallback(
    async (silent = false) => {
      try {
        const [r, s, t] = await Promise.all([api.listRoutes(), api.listSources(), api.listTargets()]);
        setRoutes(r);
        setSources(s);
        setTargets(t);
      } catch (err) {
        if (!silent) notify(err instanceof Error ? err.message : 'Failed to load routes', 'error');
      } finally {
        setLoading(false);
      }
    },
    [notify]
  );

  useEffect(() => {
    void load();
  }, [load]);

  const bulkCount = useMemo(() => bulkSources.length * bulkTargets.length, [bulkSources, bulkTargets]);

  const openCreate = () => {
    setEditing(null);
    setBulkMode(false);
    setForm({
      name: '',
      description: '',
      source_channel_id: sources[0] ? String(sources[0].id) : '',
      target_channel_id: targets[0] ? String(targets[0].id) : '',
      is_enabled: true,
      priority: 100,
    });
    setBulkSources([]);
    setBulkTargets([]);
    setFilters(defaultFilters());
    setCreateOpen(true);
  };

  const openEdit = (r: PublishingRoute) => {
    setEditing(r);
    setBulkMode(false);
    setForm({
      name: r.name,
      description: r.description || '',
      source_channel_id: String(r.source_channel_id),
      target_channel_id: String(r.target_channel_id),
      is_enabled: r.is_enabled,
      priority: r.priority,
    });
    setCreateOpen(true);
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      if (editing) {
        await api.updateRoute(editing.id, {
          name: form.name.trim(),
          description: form.description.trim() || null,
          is_enabled: form.is_enabled,
          priority: Number(form.priority) || 100,
        });
        notify(tr('تم تحديث المسار', 'Route updated'), 'success');
      } else if (bulkMode) {
        if (bulkSources.length === 0 || bulkTargets.length === 0) {
          throw new Error(tr('اختر مصدرًا واحدًا على الأقل ووجهة واحدة على الأقل', 'Select at least one source and one target'));
        }
        const created = await api.createBulkRoutes({
          name_prefix: bulkName.trim() || 'Route',
          source_channel_ids: bulkSources,
          target_channel_ids: bulkTargets,
          is_enabled: form.is_enabled,
          filters,
        });
        notify(
          tr(`تم إنشاء ${created.length} مسار نشر`, `${created.length} publishing route(s) created`),
          'success'
        );
      } else {
        await api.createRoute({
          name: form.name.trim(),
          description: form.description.trim() || null,
          source_channel_id: Number(form.source_channel_id),
          target_channel_id: Number(form.target_channel_id),
          is_enabled: form.is_enabled,
          priority: Number(form.priority) || 100,
          filters,
        });
        notify(tr('تم إنشاء مسار النشر', 'Route created'), 'success');
      }
      setCreateOpen(false);
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

  const typeLabel = (t: string) =>
    ({
      text: tr('نص', 'Text'),
      photo: tr('صورة', 'Photo'),
      video: tr('فيديو', 'Video'),
      document: tr('ملف', 'Document'),
      audio: tr('صوت', 'Audio'),
      voice: tr('رسالة صوتية', 'Voice'),
      album: tr('ألبوم', 'Album'),
    }[t] || t);

  if (loading) return <Spinner label={tr('جاري تحميل المسارات...', 'Loading routes...')} />;

  const canBuild = sources.length > 0 && targets.length > 0;

  return (
    <div className="space-y-5" data-testid="routes-page">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-slate-50">{tr('مسارات النشر', 'Publishing Routes')}</h1>
          <p className="mt-0.5 text-xs text-slate-500">
            {tr(
              'كل مسار مستقل (مصدر ← وجهة). الإيقاف أو الفشل في مسار لا يؤثر على غيره. يدعم 1→1 و1→N وN→1 وN→N.',
              'Every route is independent (source → target). Pausing or failing one never affects others. Supports 1→1, 1→N, N→1 and N→N.'
            )}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button size="sm" variant="secondary" icon={<RefreshCw className="h-3.5 w-3.5" />} onClick={() => load(true)}>
            {tr('تحديث', 'Refresh')}
          </Button>
          <Button icon={<Plus className="h-4 w-4" />} onClick={openCreate} disabled={!canBuild}>
            {tr('إنشاء مسار', 'Create route')}
          </Button>
        </div>
      </div>

      {!canBuild && (
        <div className="rounded-xl border border-amber-800/60 bg-amber-950/30 px-4 py-3 text-xs text-amber-300">
          {tr(
            'يجب إضافة قناة مصدر واحدة ووجهة واحدة على الأقل قبل إنشاء المسارات.',
            'Add at least one source channel and one target channel before creating routes.'
          )}
        </div>
      )}

      <Card title={`${routes.length} ${tr('مسار', 'routes')} · ${routes.filter((r) => r.is_enabled).length} ${tr('نشط', 'active')}`}>
        {routes.length === 0 ? (
          <EmptyState
            title={tr('لا توجد مسارات بعد', 'No routes yet')}
            subtitle={tr(
              'استخدم أداة الربط المتعدد لإنشاء N×M مسارًا في خطوة واحدة، أو أنشئ مسارًا واحدًا مع قواعد تصفية.',
              'Use the bulk builder to create N×M routes at once, or create a single route with filters.'
            )}
            action={
              canBuild ? (
                <Button icon={<Wand2 className="h-4 w-4" />} onClick={openCreate}>
                  {tr('بدء الإعداد', 'Start setup')}
                </Button>
              ) : undefined
            }
          />
        ) : (
          <div className="space-y-2">
            {routes.map((r) => (
              <div
                key={r.id}
                className="flex flex-wrap items-center gap-3 rounded-xl border border-slate-800 bg-slate-950/40 px-3 py-2.5"
              >
                <div className="flex min-w-[200px] flex-1 items-center gap-2 sm:min-w-[280px]">
                  <GitBranch className={`h-4 w-4 shrink-0 ${r.is_enabled ? 'text-cyan-400' : 'text-slate-600'}`} />
                  <div className="min-w-0">
                    <p className="truncate text-xs font-semibold text-slate-100">{r.name}</p>
                    <p className="flex flex-wrap items-center gap-1 truncate text-[11px] text-slate-500">
                      <span className="font-mono">{r.source_title}</span>
                      <ArrowRight className="h-3 w-3 rtl:rotate-180" />
                      <span className="font-mono">{r.target_title}</span>
                    </p>
                  </div>
                </div>

                <div className="flex flex-wrap items-center gap-1" data-testid={`route-chips-${r.id}`}>
                  <Badge tone={r.is_enabled ? 'green' : 'slate'}>{r.is_enabled ? tr('نشط', 'Active') : tr('متوقف', 'Paused')}</Badge>
                  <Badge tone="slate">#{r.id}</Badge>
                  <Badge tone="blue">
                    {r.filters.allowed_content_types.length === ALL_TYPES.length
                      ? tr('كل الأنواع', 'all types')
                      : r.filters.allowed_content_types.map(typeLabel).join(', ')}
                  </Badge>
                  {(r.filters.include_keywords.length > 0 || r.filters.exclude_keywords.length > 0) && (
                    <Badge tone="amber">
                      <Filter className="h-3 w-3" /> {tr('قواعد كلمات', 'keywords')}
                    </Badge>
                  )}
                  {r.filters.target_signature && (
                    <Badge tone="cyan">
                      {tr('توقيع', 'signature')}: {r.filters.target_signature}
                    </Badge>
                  )}
                </div>

                <p className="hidden text-[10px] text-slate-600 xl:block">{formatDateTime(r.updated_at, lang)}</p>

                <div className="flex items-center gap-1">
                  <Toggle
                    checked={r.is_enabled}
                    onChange={() => action(r.id, tr('تم تبديل حالة المسار', 'Route toggled'), () => api.toggleRoute(r.id))}
                  />
                  <Button
                    size="sm"
                    variant="secondary"
                    icon={<Filter className="h-3.5 w-3.5" />}
                    onClick={() => setFilterRoute(r)}
                  >
                    {tr('القواعد', 'Filters')}
                  </Button>
                  <Button size="sm" variant="ghost" icon={<Pencil className="h-3.5 w-3.5" />} onClick={() => openEdit(r)}>
                    {tr('تعديل', 'Edit')}
                  </Button>
                  <Button size="sm" variant="danger" icon={<Trash2 className="h-3.5 w-3.5" />} onClick={() => setDeleteTarget(r)}>
                    {tr('حذف', 'Delete')}
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>

      {/* Create / edit modal */}
      <Modal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        wide
        title={editing ? tr('تعديل مسار النشر', 'Edit publishing route') : tr('إنشاء مسار نشر', 'Create publishing route')}
        footer={
          <>
            <Button variant="secondary" onClick={() => setCreateOpen(false)}>
              {tr('إلغاء', 'Cancel')}
            </Button>
            <Button form="route-form" type="submit" loading={saving}>
              {editing
                ? tr('حفظ التعديلات', 'Save changes')
                : bulkMode
                ? tr(`إنشاء ${bulkCount} مسار`, `Create ${bulkCount} route(s)`)
                : tr('إنشاء المسار', 'Create route')}
            </Button>
          </>
        }
      >
        <form id="route-form" onSubmit={submit} className="space-y-4">
          {!editing && (
            <div className="flex items-center gap-2 rounded-xl border border-slate-800 bg-slate-950/50 p-1">
              <button
                type="button"
                onClick={() => setBulkMode(false)}
                className={`flex-1 rounded-lg px-3 py-1.5 text-xs font-medium ${
                  !bulkMode ? 'bg-cyan-500/20 text-cyan-300' : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                {tr('مسار واحد', 'Single route')}
              </button>
              <button
                type="button"
                onClick={() => setBulkMode(true)}
                className={`flex flex-1 items-center justify-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium ${
                  bulkMode ? 'bg-cyan-500/20 text-cyan-300' : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                <Wand2 className="h-3.5 w-3.5" />
                {tr('ربط متعدد N×M', 'Bulk N×M builder')}
              </button>
            </div>
          )}

          {!bulkMode && (
            <>
              <Input
                label={tr('اسم المسار', 'Route name')}
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                required
                maxLength={200}
                placeholder="Source A → Target 1"
              />
              <Textarea
                label={tr('وصف (اختياري)', 'Description (optional)')}
                value={form.description}
                onChange={(e) => setForm({ ...form, description: e.target.value })}
                rows={2}
                maxLength={1000}
              />
              <div className="grid gap-3 sm:grid-cols-2">
                <Select
                  label={tr('قناة المصدر', 'Source channel')}
                  value={form.source_channel_id}
                  onChange={(e) => setForm({ ...form, source_channel_id: e.target.value })}
                  disabled={!!editing}
                  required
                >
                  <option value="">—</option>
                  {sources.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.title} ({s.username ? `@${s.username}` : s.identifier})
                    </option>
                  ))}
                </Select>
                <Select
                  label={tr('قناة الوجهة', 'Target channel')}
                  value={form.target_channel_id}
                  onChange={(e) => setForm({ ...form, target_channel_id: e.target.value })}
                  disabled={!!editing}
                  required
                >
                  <option value="">—</option>
                  {targets.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.title} ({t.username ? `@${t.username}` : t.identifier})
                    </option>
                  ))}
                </Select>
              </div>
            </>
          )}

          {bulkMode && (
            <div className="space-y-3">
              <Input
                label={tr('بادئة اسم المسار', 'Route name prefix')}
                value={bulkName}
                onChange={(e) => setBulkName(e.target.value)}
                maxLength={120}
              />
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3">
                  <p className="mb-2 text-xs font-semibold text-slate-300">
                    {tr('المصادر', 'Sources')} ({bulkSources.length})
                  </p>
                  <div className="max-h-44 space-y-1 overflow-y-auto">
                    {sources.map((s) => (
                      <label key={s.id} className="flex cursor-pointer items-center gap-2 rounded-md px-1.5 py-1 hover:bg-slate-800/50">
                        <input
                          type="checkbox"
                          className="h-3.5 w-3.5 accent-cyan-500"
                          checked={bulkSources.includes(s.id)}
                          onChange={(e) =>
                            setBulkSources((prev) =>
                              e.target.checked ? [...prev, s.id] : prev.filter((x) => x !== s.id)
                            )
                          }
                        />
                        <span className="truncate text-[11px] text-slate-300">{s.title}</span>
                      </label>
                    ))}
                  </div>
                </div>
                <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3">
                  <p className="mb-2 text-xs font-semibold text-slate-300">
                    {tr('الوجهات', 'Targets')} ({bulkTargets.length})
                  </p>
                  <div className="max-h-44 space-y-1 overflow-y-auto">
                    {targets.map((t) => (
                      <label key={t.id} className="flex cursor-pointer items-center gap-2 rounded-md px-1.5 py-1 hover:bg-slate-800/50">
                        <input
                          type="checkbox"
                          className="h-3.5 w-3.5 accent-cyan-500"
                          checked={bulkTargets.includes(t.id)}
                          onChange={(e) =>
                            setBulkTargets((prev) =>
                              e.target.checked ? [...prev, t.id] : prev.filter((x) => x !== t.id)
                            )
                          }
                        />
                        <span className="truncate text-[11px] text-slate-300">{t.title}</span>
                      </label>
                    ))}
                  </div>
                </div>
              </div>
              <div className="rounded-lg border border-cyan-900/60 bg-cyan-950/30 px-3 py-2 text-[11px] text-cyan-300">
                {tr('سيتم إنشاء', 'Will create')} <strong>{bulkCount}</strong>{' '}
                {tr('مسارًا (كل مصدر ← كل وجهة). المسارات الموجودة مسبقًا يتم تخطيها دون خطأ.', 'routes (every source → every target). Existing duplicates are skipped without error.')}
              </div>
            </div>
          )}

          <div className="grid gap-3 sm:grid-cols-2">
            <Input
              label={tr('الأولوية', 'Priority')}
              type="number"
              min={1}
              max={1000}
              value={form.priority}
              onChange={(e) => setForm({ ...form, priority: Number(e.target.value) })}
            />
            <div className="flex items-end gap-2 pb-1">
              <Toggle checked={form.is_enabled} onChange={(next) => setForm({ ...form, is_enabled: next })} />
              <span className="text-xs text-slate-300">{tr('تشغيل المسار فور الإنشاء', 'Enable route immediately')}</span>
            </div>
          </div>

          {!editing && (
            <FilterEditor filters={filters} onChange={setFilters} typeLabel={typeLabel} />
          )}
        </form>
      </Modal>

      {/* Filters modal for existing route */}
      <FiltersModal route={filterRoute} onClose={() => setFilterRoute(null)} onSaved={() => load(true)} typeLabel={typeLabel} />

      <ConfirmDialog
        open={!!deleteTarget}
        title={tr('حذف مسار النشر', 'Delete publishing route')}
        message={tr(
          `سيتم حذف المسار «${deleteTarget?.name || ''}» فقط دون التأثير على المصادر أو الوجهات أو بقية المسارات. هل تريد المتابعة؟`,
          `Only the route "${deleteTarget?.name || ''}" will be deleted; sources, targets and other routes stay untouched. Continue?`
        )}
        confirmLabel={tr('حذف', 'Delete')}
        cancelLabel={tr('إلغاء', 'Cancel')}
        onCancel={() => setDeleteTarget(null)}
        onConfirm={async () => {
          const target = deleteTarget;
          setDeleteTarget(null);
          if (target) await action(target.id, tr('تم حذف المسار', 'Route deleted'), () => api.deleteRoute(target.id));
        }}
      />
    </div>
  );
};

/* ------------------------------------------------------------------ */
/* Shared filter editor                                                */
/* ------------------------------------------------------------------ */
const FilterEditor: React.FC<{
  filters: RouteFilterConfig;
  onChange: (next: RouteFilterConfig) => void;
  typeLabel: (t: string) => string;
}> = ({ filters, onChange, typeLabel }) => {
  const { tr } = useI18n();
  const set = <K extends keyof RouteFilterConfig>(key: K, value: RouteFilterConfig[K]) =>
    onChange({ ...filters, [key]: value });

  // Comma separated inputs keep their own raw text so that trailing commas / spaces are
  // not swallowed while the user is still typing (the parsed array is the source of truth
  // for the API payload only).
  const [rawKeywords, setRawKeywords] = React.useState({
    include: filters.include_keywords.join(', '),
    exclude: filters.exclude_keywords.join(', '),
    extensions: filters.allowed_extensions.join(', '),
  });

  React.useEffect(() => {
    setRawKeywords({
      include: filters.include_keywords.join(', '),
      exclude: filters.exclude_keywords.join(', '),
      extensions: filters.allowed_extensions.join(', '),
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="space-y-3 rounded-xl border border-slate-800 bg-slate-950/40 p-3.5">
      <div className="flex items-center justify-between">
        <p className="flex items-center gap-1.5 text-xs font-semibold text-slate-200">
          <Filter className="h-3.5 w-3.5" /> {tr('قواعد التصفية والتحكم', 'Filtering & transformation rules')}
        </p>
        <button
          type="button"
          onClick={() =>
            set(
              'allowed_content_types',
              filters.allowed_content_types.length === ALL_TYPES.length ? [] : [...ALL_TYPES]
            )
          }
          className="text-[11px] text-cyan-400 hover:text-cyan-300"
        >
          {filters.allowed_content_types.length === ALL_TYPES.length
            ? tr('إلغاء الكل', 'Clear all')
            : tr('تحديد الكل', 'Select all')}
        </button>
      </div>

      <div>
        <p className="mb-1.5 text-[11px] text-slate-400">{tr('أنواع المحتوى المسموح بها', 'Allowed content types')}</p>
        <div className="flex flex-wrap gap-1.5">
          {ALL_TYPES.map((t) => {
            const active = filters.allowed_content_types.includes(t);
            return (
              <button
                key={t}
                type="button"
                onClick={() =>
                  set(
                    'allowed_content_types',
                    active ? filters.allowed_content_types.filter((x) => x !== t) : [...filters.allowed_content_types, t]
                  )
                }
                className={`rounded-md border px-2 py-1 text-[11px] transition-colors ${
                  active
                    ? 'border-cyan-600/60 bg-cyan-500/15 text-cyan-300'
                    : 'border-slate-700 bg-slate-800/40 text-slate-500 hover:text-slate-300'
                }`}
              >
                {typeLabel(t)}
              </button>
            );
          })}
        </div>
        {filters.allowed_content_types.length === 0 && (
          <p className="mt-1 text-[11px] text-amber-400">
            {tr('لا توجد أنواع مسموحة — سيتم تخطي كل المنشورات (SKIPPED).', 'No types allowed — every post will be SKIPPED.')}
          </p>
        )}
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <Input
          label={tr('كلمات يجب توفرها (مفصولة بفاصلة)', 'Include keywords (comma separated)')}
          value={rawKeywords.include}
          onChange={(e) => {
            setRawKeywords((prev) => ({ ...prev, include: e.target.value }));
            set('include_keywords', csvToArr(e.target.value));
          }}
          placeholder="عاجل, news"
        />
        <Input
          label={tr('كلمات يجب استبعادها', 'Exclude keywords (comma separated)')}
          value={rawKeywords.exclude}
          onChange={(e) => {
            setRawKeywords((prev) => ({ ...prev, exclude: e.target.value }));
            set('exclude_keywords', csvToArr(e.target.value));
          }}
          placeholder="إعلان, promo"
        />
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <Input
          label={tr('أدنى طول نص', 'Min text length')}
          type="number"
          min={0}
          value={filters.min_text_length ?? ''}
          onChange={(e) => set('min_text_length', e.target.value === '' ? null : Number(e.target.value))}
        />
        <Input
          label={tr('أقصى طول نص', 'Max text length')}
          type="number"
          min={1}
          value={filters.max_text_length ?? ''}
          onChange={(e) => set('max_text_length', e.target.value === '' ? null : Number(e.target.value))}
        />
      </div>

      <Input
        label={tr('امتدادات الملفات المسموحة', 'Allowed file extensions')}
        value={rawKeywords.extensions}
        onChange={(e) => {
          setRawKeywords((prev) => ({ ...prev, extensions: e.target.value }));
          set('allowed_extensions', csvToArr(e.target.value));
        }}
        placeholder=".pdf, .zip, .mp4"
        hint={tr('اتركه فارغًا للسماح بكل الامتدادات.', 'Leave empty to allow every extension.')}
      />

      <div className="grid gap-3 sm:grid-cols-2">
        <Textarea
          label={tr('نص يُضاف قبل المنشور', 'Prefix text')}
          value={filters.prefix_text ?? ''}
          onChange={(e) => set('prefix_text', e.target.value || null)}
          rows={2}
          maxLength={1000}
        />
        <Textarea
          label={tr('نص يُضاف بعد المنشور', 'Suffix text')}
          value={filters.suffix_text ?? ''}
          onChange={(e) => set('suffix_text', e.target.value || null)}
          rows={2}
          maxLength={1000}
        />
      </div>

      <Input
        label={tr('توقيع خاص بالوجهة', 'Target signature')}
        value={filters.target_signature ?? ''}
        onChange={(e) => set('target_signature', e.target.value || null)}
        maxLength={500}
        placeholder="@my_channel"
      />

      <div className="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-900/60 px-3 py-2">
        <div>
          <p className="text-xs text-slate-200">{tr('حذف الروابط من النص', 'Strip URLs from text')}</p>
          <p className="text-[10px] text-slate-500">
            {tr('يزيل الروابط من المنشور قبل النشر في الوجهة.', 'Removes links from the post before publishing to the target.')}
          </p>
        </div>
        <Toggle checked={filters.strip_urls} onChange={(next) => set('strip_urls', next)} />
      </div>
    </div>
  );
};

const FiltersModal: React.FC<{
  route: PublishingRoute | null;
  onClose: () => void;
  onSaved: () => void;
  typeLabel: (t: string) => string;
}> = ({ route, onClose, onSaved, typeLabel }) => {
  const { tr } = useI18n();
  const { notify } = useToast();
  const [draft, setDraft] = useState<RouteFilterConfig>(defaultFilters());
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (route) setDraft({ ...defaultFilters(), ...route.filters });
  }, [route]);

  if (!route) return null;

  return (
    <Modal
      open={!!route}
      onClose={onClose}
      wide
      title={`${tr('قواعد المسار', 'Route filters')} — ${route.name}`}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            {tr('إلغاء', 'Cancel')}
          </Button>
          <Button
            loading={saving}
            icon={<Power className="h-4 w-4" />}
            onClick={async () => {
              setSaving(true);
              try {
                await api.updateRoute(route.id, { filters: draft });
                notify(tr('تم حفظ قواعد المسار', 'Route filters saved'), 'success');
                onSaved();
                onClose();
              } catch (err) {
                notify(err instanceof Error ? err.message : 'Save failed', 'error');
              } finally {
                setSaving(false);
              }
            }}
          >
            {tr('حفظ القواعد', 'Save filters')}
          </Button>
        </>
      }
    >
      <FilterEditor filters={draft} onChange={setDraft} typeLabel={typeLabel} />
    </Modal>
  );
};
