import React, { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { api, getStoredToken, setStoredToken } from '../services/api';
import type { User } from '../types';
import { useI18n } from './I18nContext';

interface AuthContextValue {
  user: User | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  setUserFromToken: (token: string, user: User) => void;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const { setLang } = useI18n();

  const refreshUser = useCallback(async () => {
    const token = getStoredToken();
    if (!token) {
      setUser(null);
      setLoading(false);
      return;
    }
    try {
      const me = await api.me();
      setUser(me);
    } catch {
      setStoredToken(null);
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refreshUser();
    const onUnauth = () => setUser(null);
    window.addEventListener('tap:unauthorized', onUnauth);
    return () => window.removeEventListener('tap:unauthorized', onUnauth);
  }, [refreshUser]);

  const login = useCallback(
    async (username: string, password: string) => {
      const res = await api.login(username, password);
      setStoredToken(res.access_token);
      setUser(res.user);
      if (res.user.preferred_language === 'ar' || res.user.preferred_language === 'en') {
        setLang(res.user.preferred_language);
      }
    },
    [setLang]
  );

  const setUserFromToken = useCallback((token: string, nextUser: User) => {
    setStoredToken(token);
    setUser(nextUser);
  }, []);

  const logout = useCallback(() => {
    setStoredToken(null);
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, setUserFromToken, refreshUser }}>
      {children}
    </AuthContext.Provider>
  );
};

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
