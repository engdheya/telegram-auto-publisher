import React, { createContext, useCallback, useContext, useEffect, useState } from 'react';
import type { Language } from '../types';

const translations = {
  ar: {
    appName: 'الناشر التلقائي لتيليجرام',
    appSubtitle: 'نظام مراقبة ونشر متعدد المسارات جاهز للإنتاج',
    navDashboard: 'لوحة المؤشرات',
    navTelegram: 'حساب تيليجرام',
    navSources: 'قنوات المصدر',
    navTargets: 'قنوات الوجهة',
    navRoutes: 'مسارات النشر',
    navMessages: 'سجل المنشورات',
    navQueue: 'إدارة الطابور',
    navLogs: 'السجلات والعمليات',
    navSettings: 'الإعدادات والنسخ الاحتياطي',
    logout: 'تسجيل الخروج',
    loginTitle: 'تسجيل الدخول إلى لوحة التحكم',
    loginSubtitle: 'أدخل بيانات حساب المشرف أو المشغّل للوصول إلى النظام',
    username: 'اسم المستخدم',
    password: 'كلمة المرور',
    signIn: 'دخول إلى النظام',
    signingIn: 'جاري التحقق...',
    telegramConnected: 'متصل بتيليجرام',
    telegramDisconnected: 'غير متصل بتيليجرام',
    workerRunning: 'محرك المهام نشط',
    workerOffline: 'محرك المهام متوقف',
    walHealthy: 'قاعدة البيانات WAL سليمة',
    sourcesCount: 'قنوات المصدر',
    targetsCount: 'قنوات الوجهة',
    activeRoutesCount: 'المسارات النشطة',
    receivedPostsCount: 'المنشورات المستلمة',
    publishedCount: 'المنشورات الناجحة',
    failedCount: 'المهام الفاشلة',
    waitingCount: 'المهام المنتظرة',
    unknownCount: 'تحتاج مراجعة (UNKNOWN)',
    recentActivity: 'آخر الأنشطة والعمليات',
    refresh: 'تحديث',
    add: 'إضافة',
    save: 'حفظ',
    cancel: 'إلغاء',
    delete: 'حذف',
    edit: 'تعديل',
    verify: 'فحص الصلاحية',
    search: 'بحث...',
    noData: 'لا توجد سجلات مطابقة حاليًا',
    switchLang: 'English',
  },
  en: {
    appName: 'Telegram Auto Publisher',
    appSubtitle: 'Production Multi-Route Channel Relay Engine',
    navDashboard: 'Dashboard',
    navTelegram: 'Telegram Account',
    navSources: 'Sources',
    navTargets: 'Targets',
    navRoutes: 'Routes & Filters',
    navMessages: 'Publishing History',
    navQueue: 'Queue Management',
    navLogs: 'Audit & Error Logs',
    navSettings: 'Settings & Backups',
    logout: 'Sign Out',
    loginTitle: 'Sign in to Control Dashboard',
    loginSubtitle: 'Enter administrator or operator credentials to manage publishing pipelines',
    username: 'Username',
    password: 'Password',
    signIn: 'Sign In',
    signingIn: 'Signing in...',
    telegramConnected: 'Telegram Connected',
    telegramDisconnected: 'Telegram Disconnected',
    workerRunning: 'Worker Online',
    workerOffline: 'Worker Standby',
    walHealthy: 'SQLite WAL Healthy',
    sourcesCount: 'Source Channels',
    targetsCount: 'Target Channels',
    activeRoutesCount: 'Active Routes',
    receivedPostsCount: 'Received Posts',
    publishedCount: 'Published Jobs',
    failedCount: 'Failed Jobs',
    waitingCount: 'Waiting in Queue',
    unknownCount: 'Needs Review (UNKNOWN)',
    recentActivity: 'Recent Operational Activity',
    refresh: 'Refresh',
    add: 'Add',
    save: 'Save',
    cancel: 'Cancel',
    delete: 'Delete',
    edit: 'Edit',
    verify: 'Verify',
    search: 'Search...',
    noData: 'No matching records found',
    switchLang: 'العربية',
  },
} as const;

type TranslationKey = keyof typeof translations.ar;

interface I18nContextValue {
  lang: Language;
  isRtl: boolean;
  setLang: (l: Language) => void;
  t: (key: TranslationKey) => string;
  tr: (arText: string, enText: string) => string;
}

const I18nContext = createContext<I18nContextValue | undefined>(undefined);

export const I18nProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [lang, setLangState] = useState<Language>(() => {
    const saved = localStorage.getItem('tap_lang');
    return saved === 'en' ? 'en' : 'ar';
  });

  const setLang = useCallback((next: Language) => {
    setLangState(next);
    localStorage.setItem('tap_lang', next);
  }, []);

  useEffect(() => {
    document.documentElement.lang = lang;
    document.documentElement.dir = lang === 'ar' ? 'rtl' : 'ltr';
  }, [lang]);

  const t = useCallback(
    (key: TranslationKey) => translations[lang][key] ?? key,
    [lang]
  );

  const tr = useCallback(
    (arText: string, enText: string) => (lang === 'ar' ? arText : enText),
    [lang]
  );

  return (
    <I18nContext.Provider value={{ lang, isRtl: lang === 'ar', setLang, t, tr }}>
      {children}
    </I18nContext.Provider>
  );
};

export function useI18n(): I18nContextValue {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error('useI18n must be used within I18nProvider');
  return ctx;
}
