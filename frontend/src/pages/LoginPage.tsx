import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Languages, Lock, ShieldCheck, User as UserIcon, Send } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { useI18n } from '../contexts/I18nContext';
import { Button, Input } from '../components/ui';
import logo from '../assets/logo.svg';

export const LoginPage: React.FC = () => {
  const { login, user } = useAuth();
  const { t, tr, lang, setLang } = useI18n();
  const navigate = useNavigate();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  React.useEffect(() => {
    if (user) navigate('/', { replace: true });
  }, [user, navigate]);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await login(username.trim(), password);
      navigate('/', { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : tr('تعذر تسجيل الدخول', 'Unable to sign in'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-slate-950 px-4 py-10">
      <div className="pointer-events-none absolute -top-40 -start-40 h-96 w-96 rounded-full bg-cyan-600/20 blur-3xl" />
      <div className="pointer-events-none absolute -bottom-40 -end-40 h-96 w-96 rounded-full bg-teal-600/15 blur-3xl" />

      <div className="relative w-full max-w-md">
        <div className="mb-6 flex items-center justify-center gap-3">
          <img src={logo} alt="" className="h-12 w-12 rounded-xl" />
          <div>
            <h1 className="text-lg font-bold text-slate-50">{t('appName')}</h1>
            <p className="text-[11px] text-slate-500">Telegram Auto Publisher</p>
          </div>
        </div>

        <div className="rounded-2xl border border-slate-800 bg-slate-900/80 p-6 shadow-2xl backdrop-blur">
          <div className="mb-5 flex items-start justify-between gap-3">
            <div>
              <h2 className="text-base font-semibold text-slate-100">{t('loginTitle')}</h2>
              <p className="mt-1 text-xs leading-relaxed text-slate-500">{t('loginSubtitle')}</p>
            </div>
            <button
              type="button"
              onClick={() => setLang(lang === 'ar' ? 'en' : 'ar')}
              className="flex shrink-0 items-center gap-1 rounded-lg border border-slate-700 bg-slate-800/60 px-2 py-1 text-[11px] text-slate-300 hover:bg-slate-700/60"
            >
              <Languages className="h-3.5 w-3.5" />
              {t('switchLang')}
            </button>
          </div>

          <form onSubmit={onSubmit} className="space-y-4">
            <div className="relative">
              <Input
                label={t('username')}
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
                required
                minLength={2}
                placeholder="admin"
                data-testid="login-username"
              />
              <UserIcon className="pointer-events-none absolute end-3 top-[34px] h-4 w-4 text-slate-500" />
            </div>
            <div className="relative">
              <Input
                label={t('password')}
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                required
                minLength={6}
                placeholder="••••••••"
                data-testid="login-password"
              />
              <Lock className="pointer-events-none absolute end-3 top-[34px] h-4 w-4 text-slate-500" />
            </div>

            {error && (
              <div
                role="alert"
                className="rounded-lg border border-rose-800/60 bg-rose-950/50 px-3 py-2 text-xs text-rose-300"
              >
                {error}
              </div>
            )}

            <Button type="submit" loading={loading} className="w-full" data-testid="login-submit">
              {loading ? t('signingIn') : t('signIn')}
            </Button>
          </form>

          <div className="mt-5 flex items-start gap-2 rounded-lg border border-slate-800 bg-slate-950/50 px-3 py-2.5">
            <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-emerald-400" />
            <p className="text-[11px] leading-relaxed text-slate-500">
              {tr(
                'الجلسة محمية بـ JWT مع تشفير كلمات المرور Argon2id. لا تُسجَّل كلمات المرور أو رموز التحقق في أي مكان.',
                'Sessions are protected with JWT and Argon2id password hashing. Passwords and OTP codes are never logged.'
              )}
            </p>
          </div>
        </div>

        <p className="mt-5 flex items-center justify-center gap-1.5 text-center text-[11px] text-slate-600">
          <Send className="h-3 w-3" />
          {tr('نظام مراقبة وإعادة نشر قنوات تيليجرام', 'Telegram channel monitoring & relay engine')}
        </p>
      </div>
    </div>
  );
};
