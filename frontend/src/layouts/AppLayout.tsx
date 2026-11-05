import React, { useState } from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import {
  LayoutDashboard,
  Send,
  Inbox,
  Target,
  GitBranch,
  MessageSquare,
  ListChecks,
  ScrollText,
  Settings,
  LogOut,
  Menu,
  X,
  Languages,
  UserCircle2,
} from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { useI18n } from '../contexts/I18nContext';
import logo from '../assets/logo.svg';

const NAV_ITEMS = [
  { to: '/', key: 'navDashboard', icon: LayoutDashboard, end: true },
  { to: '/telegram', key: 'navTelegram', icon: Send },
  { to: '/sources', key: 'navSources', icon: Inbox },
  { to: '/targets', key: 'navTargets', icon: Target },
  { to: '/routes', key: 'navRoutes', icon: GitBranch },
  { to: '/messages', key: 'navMessages', icon: MessageSquare },
  { to: '/queue', key: 'navQueue', icon: ListChecks },
  { to: '/logs', key: 'navLogs', icon: ScrollText },
  { to: '/settings', key: 'navSettings', icon: Settings },
] as const;

export const AppLayout: React.FC = () => {
  const { user, logout } = useAuth();
  const { t, lang, setLang, isRtl } = useI18n();
  const navigate = useNavigate();
  const [mobileOpen, setMobileOpen] = useState(false);

  const handleLogout = () => {
    logout();
    navigate('/login', { replace: true });
  };

  const sidebar = (
    <div className="flex h-full flex-col bg-slate-900/95">
      <div className="flex items-center gap-3 border-b border-slate-800 px-4 py-4">
        <img src={logo} alt="" className="h-9 w-9 rounded-lg" />
        <div className="min-w-0">
          <p className="truncate text-sm font-bold text-slate-50">{t('appName')}</p>
          <p className="truncate text-[10px] text-slate-500">{t('appSubtitle')}</p>
        </div>
      </div>

      <nav className="flex-1 space-y-1 overflow-y-auto px-2 py-3" aria-label="Main navigation">
        {NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          return (
            <NavLink
              key={item.to}
              to={item.to}
              end={'end' in item ? item.end : false}
              onClick={() => setMobileOpen(false)}
              className={({ isActive }) =>
                `flex items-center gap-2.5 rounded-lg px-3 py-2 text-[13px] font-medium transition-colors ${
                  isActive
                    ? 'bg-cyan-500/15 text-cyan-300 ring-1 ring-inset ring-cyan-500/30'
                    : 'text-slate-400 hover:bg-slate-800/60 hover:text-slate-200'
                }`
              }
            >
              <Icon className="h-4 w-4 shrink-0" />
              <span className="truncate">{t(item.key)}</span>
            </NavLink>
          );
        })}
      </nav>

      <div className="border-t border-slate-800 p-3">
        <div className="mb-2 flex items-center gap-2 rounded-lg bg-slate-950/50 px-2.5 py-2">
          <UserCircle2 className="h-6 w-6 shrink-0 text-cyan-400" />
          <div className="min-w-0 flex-1">
            <p className="truncate text-xs font-semibold text-slate-200">{user?.username}</p>
            <p className="truncate text-[10px] uppercase tracking-wide text-slate-500">{user?.role}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setLang(lang === 'ar' ? 'en' : 'ar')}
            className="flex flex-1 items-center justify-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800/60 px-2 py-1.5 text-[11px] font-medium text-slate-300 hover:bg-slate-700/60"
          >
            <Languages className="h-3.5 w-3.5" />
            {t('switchLang')}
          </button>
          <button
            type="button"
            onClick={handleLogout}
            className="flex items-center justify-center gap-1.5 rounded-lg border border-rose-900/60 bg-rose-950/40 px-2 py-1.5 text-[11px] font-medium text-rose-300 hover:bg-rose-900/40"
          >
            <LogOut className="h-3.5 w-3.5" />
            {t('logout')}
          </button>
        </div>
      </div>
    </div>
  );

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      {/* Desktop sidebar */}
      <aside
        className={`fixed inset-y-0 z-30 hidden w-64 border-slate-800 lg:block ${
          isRtl ? 'right-0 border-l' : 'left-0 border-r'
        }`}
      >
        {sidebar}
      </aside>

      {/* Mobile drawer */}
      {mobileOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-slate-950/80 backdrop-blur-sm" onClick={() => setMobileOpen(false)} />
          <aside
            className={`absolute inset-y-0 w-64 border-slate-800 ${
              isRtl ? 'right-0 border-l' : 'left-0 border-r'
            }`}
          >
            <button
              type="button"
              className="absolute end-2 top-3 z-10 rounded-md p-1 text-slate-400 hover:text-slate-100"
              onClick={() => setMobileOpen(false)}
              aria-label="Close menu"
            >
              <X className="h-5 w-5" />
            </button>
            {sidebar}
          </aside>
        </div>
      )}

      <div className={isRtl ? 'lg:pr-64' : 'lg:pl-64'}>
        <header className="sticky top-0 z-20 flex items-center gap-3 border-b border-slate-800 bg-slate-950/85 px-4 py-3 backdrop-blur">
          <button
            type="button"
            className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-800 hover:text-slate-100 lg:hidden"
            onClick={() => setMobileOpen(true)}
            aria-label="Open menu"
          >
            <Menu className="h-5 w-5" />
          </button>
          <div className="flex items-center gap-2 lg:hidden">
            <img src={logo} alt="" className="h-7 w-7 rounded" />
            <span className="text-sm font-bold">{t('appName')}</span>
          </div>
          <div className="hidden flex-1 lg:block">
            <p className="text-xs text-slate-500">{t('appSubtitle')}</p>
          </div>
          <button
            type="button"
            onClick={() => setLang(lang === 'ar' ? 'en' : 'ar')}
            className="ms-auto flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-900 px-2.5 py-1.5 text-[11px] font-medium text-slate-300 hover:bg-slate-800 lg:hidden"
          >
            <Languages className="h-3.5 w-3.5" />
            {t('switchLang')}
          </button>
        </header>

        <main className="mx-auto w-full max-w-[1400px] px-4 py-5 sm:px-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
};
