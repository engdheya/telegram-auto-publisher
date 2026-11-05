import { describe, expect, it, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { LoginPage } from '../src/pages/LoginPage';
import { ApiError, api, getStoredToken, setStoredToken } from '../src/services/api';
import { mockFetch, renderWithProviders, mockUser, jsonResponse } from './helpers';

describe('Authentication flow (real API contract)', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('posts credentials to /api/v1/auth/login and stores the JWT', async () => {
    const fetchMock = mockFetch({
      '/auth/login': () => ({
        access_token: 'jwt-token-abc',
        token_type: 'bearer',
        expires_in_seconds: 3600,
        user: mockUser,
      }),
      '/auth/me': () => mockUser,
    });

    renderWithProviders(<LoginPage />, { route: '/login' });

    await userEvent.type(screen.getByTestId('login-username'), 'admin');
    await userEvent.type(screen.getByTestId('login-password'), 'Admin@2026!Secure');
    await userEvent.click(screen.getByTestId('login-submit'));

    await waitFor(() => expect(getStoredToken()).toBe('jwt-token-abc'));

    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toBe('/api/v1/auth/login');
    expect(init?.method).toBe('POST');
    expect(JSON.parse(String(init?.body))).toEqual({
      username: 'admin',
      password: 'Admin@2026!Secure',
    });
  });

  it('surfaces backend error messages instead of silently failing', async () => {
    mockFetch({
      '/auth/login': () => {
        throw Object.assign(new Error('ignore'), {});
      },
    });
    // simulate a 401 by overriding fetch directly
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse({ detail: 'Invalid username or password.' }, 401)
      )
    );

    renderWithProviders(<LoginPage />, { route: '/login' });
    await userEvent.type(screen.getByTestId('login-username'), 'admin');
    await userEvent.type(screen.getByTestId('login-password'), 'wrong-password');
    await userEvent.click(screen.getByTestId('login-submit'));

    expect(await screen.findByRole('alert')).toHaveTextContent('Invalid username or password.');
    expect(getStoredToken()).toBeNull();
  });

  it('uses strictly relative /api/v1 URLs and attaches the bearer token', async () => {
    setStoredToken('token-xyz');
    const fetchMock = mockFetch({ '/dashboard/overview': () => ({ ok: true }) });

    await api.getDashboardOverview();

    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toBe('/api/v1/dashboard/overview');
    expect((init?.headers as Record<string, string>).Authorization).toBe('Bearer token-xyz');
  });

  it('clears the token and emits an unauthorized event on 401 responses', async () => {
    setStoredToken('expired-token');
    const onUnauthorized = vi.fn();
    window.addEventListener('tap:unauthorized', onUnauthorized);
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ detail: 'Not authenticated' }, 401)));

    await expect(api.listSources()).rejects.toBeInstanceOf(ApiError);
    expect(getStoredToken()).toBeNull();
    expect(onUnauthorized).toHaveBeenCalled();
    window.removeEventListener('tap:unauthorized', onUnauthorized);
  });
});
