import React, { useEffect } from 'react';
import { Loader2, X, Inbox } from 'lucide-react';
import type { JobStatus } from '../types';

/* ------------------------------------------------------------------ */
/* Card                                                                */
/* ------------------------------------------------------------------ */
export const Card: React.FC<{
  children: React.ReactNode;
  className?: string;
  title?: string;
  subtitle?: string;
  actions?: React.ReactNode;
}> = ({ children, className = '', title, subtitle, actions }) => (
  <section
    className={`rounded-2xl border border-slate-800 bg-slate-900/60 shadow-lg shadow-slate-950/30 backdrop-blur-sm ${className}`}
  >
    {(title || actions) && (
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 px-5 py-3.5">
        <div>
          {title && <h2 className="text-sm font-semibold text-slate-100">{title}</h2>}
          {subtitle && <p className="mt-0.5 text-xs text-slate-400">{subtitle}</p>}
        </div>
        {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
      </header>
    )}
    <div className="p-5">{children}</div>
  </section>
);

/* ------------------------------------------------------------------ */
/* Buttons                                                             */
/* ------------------------------------------------------------------ */
type ButtonVariant = 'primary' | 'secondary' | 'danger' | 'ghost' | 'success';

export const Button: React.FC<
  React.ButtonHTMLAttributes<HTMLButtonElement> & {
    variant?: ButtonVariant;
    loading?: boolean;
    size?: 'sm' | 'md';
    icon?: React.ReactNode;
  }
> = ({ variant = 'primary', loading = false, size = 'md', icon, children, className = '', ...rest }) => {
  const base =
    'inline-flex items-center justify-center gap-2 rounded-lg font-medium transition-all disabled:cursor-not-allowed disabled:opacity-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-offset-slate-950';
  const sizes = size === 'sm' ? 'px-2.5 py-1.5 text-xs' : 'px-3.5 py-2 text-sm';
  const variants: Record<ButtonVariant, string> = {
    primary:
      'bg-gradient-to-br from-cyan-500 to-teal-600 text-slate-950 font-semibold hover:from-cyan-400 hover:to-teal-500 focus:ring-cyan-500 shadow-md shadow-cyan-900/30',
    secondary:
      'border border-slate-700 bg-slate-800/70 text-slate-200 hover:bg-slate-700/70 focus:ring-slate-500',
    danger: 'border border-rose-800/60 bg-rose-950/40 text-rose-300 hover:bg-rose-900/50 focus:ring-rose-600',
    success:
      'border border-emerald-800/60 bg-emerald-950/40 text-emerald-300 hover:bg-emerald-900/50 focus:ring-emerald-600',
    ghost: 'text-slate-300 hover:bg-slate-800/70 focus:ring-slate-600',
  };
  return (
    <button className={`${base} ${sizes} ${variants[variant]} ${className}`} disabled={loading || rest.disabled} {...rest}>
      {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : icon}
      {children}
    </button>
  );
};

/* ------------------------------------------------------------------ */
/* Badges                                                              */
/* ------------------------------------------------------------------ */
const JOB_STATUS_STYLES: Record<string, string> = {
  QUEUED: 'border-sky-700/60 bg-sky-950/60 text-sky-300',
  PROCESSING: 'border-indigo-700/60 bg-indigo-950/60 text-indigo-300',
  PUBLISHED: 'border-emerald-700/60 bg-emerald-950/60 text-emerald-300',
  RETRY_WAIT: 'border-amber-700/60 bg-amber-950/60 text-amber-300',
  SKIPPED: 'border-slate-600/60 bg-slate-800/60 text-slate-300',
  FAILED: 'border-rose-700/60 bg-rose-950/60 text-rose-300',
  UNKNOWN: 'border-fuchsia-700/60 bg-fuchsia-950/60 text-fuchsia-300',
};

export const StatusBadge: React.FC<{ status: JobStatus | string; label?: string }> = ({ status, label }) => (
  <span
    className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-[11px] font-semibold tracking-wide ${
      JOB_STATUS_STYLES[status] || 'border-slate-700 bg-slate-800/60 text-slate-300'
    }`}
  >
    <span className="h-1.5 w-1.5 rounded-full bg-current" />
    {label || status}
  </span>
);

export const Badge: React.FC<{
  tone?: 'green' | 'red' | 'amber' | 'blue' | 'slate' | 'cyan';
  children: React.ReactNode;
  className?: string;
}> = ({ tone = 'slate', children, className = '' }) => {
  const tones = {
    green: 'border-emerald-700/60 bg-emerald-950/50 text-emerald-300',
    red: 'border-rose-700/60 bg-rose-950/50 text-rose-300',
    amber: 'border-amber-700/60 bg-amber-950/50 text-amber-300',
    blue: 'border-sky-700/60 bg-sky-950/50 text-sky-300',
    cyan: 'border-cyan-700/60 bg-cyan-950/50 text-cyan-300',
    slate: 'border-slate-700/60 bg-slate-800/50 text-slate-300',
  };
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-[11px] font-medium ${tones[tone]} ${className}`}
    >
      {children}
    </span>
  );
};

/* ------------------------------------------------------------------ */
/* Form fields                                                         */
/* ------------------------------------------------------------------ */
export const Input: React.FC<React.InputHTMLAttributes<HTMLInputElement> & { label?: string; hint?: string }> = ({
  label,
  hint,
  className = '',
  ...rest
}) => (
  <div className="block">
    <label className="block">
      {label && <span className="mb-1.5 block text-xs font-medium text-slate-300">{label}</span>}
      <input
        className={`w-full rounded-lg border border-slate-700 bg-slate-950/70 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:border-cyan-500 focus:outline-none focus:ring-2 focus:ring-cyan-500/30 ${className}`}
        {...rest}
      />
    </label>
    {hint && <span className="mt-1 block text-[11px] text-slate-500">{hint}</span>}
  </div>
);

export const Textarea: React.FC<
  React.TextareaHTMLAttributes<HTMLTextAreaElement> & { label?: string; hint?: string }
> = ({ label, hint, className = '', ...rest }) => (
  <div className="block">
    <label className="block">
      {label && <span className="mb-1.5 block text-xs font-medium text-slate-300">{label}</span>}
      <textarea
        className={`w-full rounded-lg border border-slate-700 bg-slate-950/70 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:border-cyan-500 focus:outline-none focus:ring-2 focus:ring-cyan-500/30 ${className}`}
        {...rest}
      />
    </label>
    {hint && <span className="mt-1 block text-[11px] text-slate-500">{hint}</span>}
  </div>
);

export const Select: React.FC<
  React.SelectHTMLAttributes<HTMLSelectElement> & { label?: string }
> = ({ label, className = '', children, ...rest }) => (
  <label className="block">
    {label && <span className="mb-1.5 block text-xs font-medium text-slate-300">{label}</span>}
    <select
      className={`w-full rounded-lg border border-slate-700 bg-slate-950/70 px-3 py-2 text-sm text-slate-100 focus:border-cyan-500 focus:outline-none focus:ring-2 focus:ring-cyan-500/30 ${className}`}
      {...rest}
    >
      {children}
    </select>
  </label>
);

export const Toggle: React.FC<{
  checked: boolean;
  onChange: (next: boolean) => void;
  label?: string;
  disabled?: boolean;
}> = ({ checked, onChange, label, disabled }) => (
  <button
    type="button"
    role="switch"
    aria-checked={checked}
    aria-label={label}
    disabled={disabled}
    onClick={() => onChange(!checked)}
    className={`relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors disabled:opacity-50 ${
      checked ? 'bg-cyan-500' : 'bg-slate-700'
    }`}
  >
    <span
      className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${
        checked ? 'translate-x-4' : 'translate-x-0.5'
      }`}
    />
  </button>
);

/* ------------------------------------------------------------------ */
/* Modal & Confirm                                                     */
/* ------------------------------------------------------------------ */
export const Modal: React.FC<{
  open: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
  wide?: boolean;
}> = ({ open, onClose, title, children, footer, wide }) => {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = '';
    };
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-40 flex items-start justify-center overflow-y-auto bg-slate-950/80 p-4 backdrop-blur-sm">
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={`my-6 w-full ${wide ? 'max-w-4xl' : 'max-w-lg'} rounded-2xl border border-slate-800 bg-slate-900 shadow-2xl`}
      >
        <header className="flex items-center justify-between border-b border-slate-800 px-5 py-3.5">
          <h3 className="text-sm font-semibold text-slate-100">{title}</h3>
          <button type="button" onClick={onClose} className="text-slate-400 hover:text-slate-200" aria-label="Close">
            <X className="h-4 w-4" />
          </button>
        </header>
        <div className="max-h-[70vh] overflow-y-auto px-5 py-4">{children}</div>
        {footer && <footer className="flex flex-wrap justify-end gap-2 border-t border-slate-800 px-5 py-3">{footer}</footer>}
      </div>
    </div>
  );
};

export const ConfirmDialog: React.FC<{
  open: boolean;
  title: string;
  message: string;
  confirmLabel: string;
  cancelLabel: string;
  danger?: boolean;
  loading?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}> = ({ open, title, message, confirmLabel, cancelLabel, danger = true, loading, onConfirm, onCancel }) => (
  <Modal
    open={open}
    onClose={onCancel}
    title={title}
    footer={
      <>
        <Button variant="secondary" onClick={onCancel}>
          {cancelLabel}
        </Button>
        <Button variant={danger ? 'danger' : 'primary'} loading={loading} onClick={onConfirm}>
          {confirmLabel}
        </Button>
      </>
    }
  >
    <p className="text-sm leading-relaxed text-slate-300">{message}</p>
  </Modal>
);

/* ------------------------------------------------------------------ */
/* Misc                                                                */
/* ------------------------------------------------------------------ */
export const Spinner: React.FC<{ label?: string }> = ({ label }) => (
  <div className="flex items-center justify-center gap-3 py-12 text-slate-400">
    <Loader2 className="h-5 w-5 animate-spin" />
    {label && <span className="text-sm">{label}</span>}
  </div>
);

export const EmptyState: React.FC<{ title: string; subtitle?: string; action?: React.ReactNode }> = ({
  title,
  subtitle,
  action,
}) => (
  <div className="flex flex-col items-center justify-center gap-3 py-12 text-center">
    <Inbox className="h-9 w-9 text-slate-600" />
    <p className="text-sm font-medium text-slate-300">{title}</p>
    {subtitle && <p className="max-w-md text-xs leading-relaxed text-slate-500">{subtitle}</p>}
    {action}
  </div>
);

export const StatCard: React.FC<{
  label: string;
  value: number | string;
  tone?: 'cyan' | 'emerald' | 'rose' | 'amber' | 'indigo' | 'fuchsia' | 'slate';
  icon?: React.ReactNode;
  hint?: string;
  testId?: string;
}> = ({ label, value, tone = 'slate', icon, hint, testId }) => {
  const tones = {
    cyan: 'from-cyan-500/15 to-transparent text-cyan-300',
    emerald: 'from-emerald-500/15 to-transparent text-emerald-300',
    rose: 'from-rose-500/15 to-transparent text-rose-300',
    amber: 'from-amber-500/15 to-transparent text-amber-300',
    indigo: 'from-indigo-500/15 to-transparent text-indigo-300',
    fuchsia: 'from-fuchsia-500/15 to-transparent text-fuchsia-300',
    slate: 'from-slate-500/15 to-transparent text-slate-300',
  };
  return (
    <div
      data-testid={testId}
      className="rounded-2xl border border-slate-800 bg-slate-900/60 p-4 shadow-lg shadow-slate-950/20"
    >
      <div className="flex items-start justify-between gap-2">
        <p className="text-xs font-medium text-slate-400">{label}</p>
        {icon && (
          <span className={`rounded-lg bg-gradient-to-br p-1.5 ${tones[tone]}`}>{icon}</span>
        )}
      </div>
      <p className="mt-2 text-2xl font-bold tabular-nums text-slate-50">{value}</p>
      {hint && <p className="mt-1 text-[11px] text-slate-500">{hint}</p>}
    </div>
  );
};

export const Pagination: React.FC<{
  page: number;
  pageSize: number;
  total: number;
  onChange: (page: number) => void;
  labels: { prev: string; next: string; showing: string };
}> = ({ page, pageSize, total, onChange, labels }) => {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  const from = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const to = Math.min(page * pageSize, total);
  return (
    <div className="flex flex-wrap items-center justify-between gap-2 border-t border-slate-800 px-1 pt-3">
      <p className="text-[11px] text-slate-500">
        {labels.showing} {from}–{to} / {total}
      </p>
      <div className="flex items-center gap-2">
        <Button size="sm" variant="secondary" disabled={page <= 1} onClick={() => onChange(page - 1)}>
          {labels.prev}
        </Button>
        <span className="text-xs tabular-nums text-slate-400">
          {page} / {pages}
        </span>
        <Button size="sm" variant="secondary" disabled={page >= pages} onClick={() => onChange(page + 1)}>
          {labels.next}
        </Button>
      </div>
    </div>
  );
};

export const formatDateTime = (iso: string | null | undefined, lang: string): string => {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(lang === 'ar' ? 'ar-EG' : 'en-GB', {
    year: 'numeric',
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
};

export const formatBytes = (bytes: number | null | undefined): string => {
  if (!bytes && bytes !== 0) return '—';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
};
