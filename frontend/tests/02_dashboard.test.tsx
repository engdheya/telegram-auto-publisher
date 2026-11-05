import { describe, expect, it } from 'vitest';
import { screen, within } from '@testing-library/react';
import { DashboardPage } from '../src/pages/DashboardPage';
import { mockDashboard, mockFetch, renderWithProviders } from './helpers';

describe('Dashboard page', () => {
  it('renders live metrics, connectivity and recent activity from the API', async () => {
    mockFetch({ '/dashboard/overview': () => mockDashboard });

    renderWithProviders(<DashboardPage />);

    expect(await screen.findByTestId('dashboard-page')).toBeInTheDocument();

    // connectivity strip
    expect(screen.getAllByText('متصل بتيليجرام').length).toBeGreaterThan(0);
    expect(screen.getByText('محرك المهام نشط')).toBeInTheDocument();
    expect(screen.getByText('قاعدة البيانات WAL سليمة')).toBeInTheDocument();

    // counters derived from the payload
    expect(within(screen.getByTestId('stat-received')).getByText('12')).toBeInTheDocument();
    expect(within(screen.getByTestId('stat-published')).getByText('9')).toBeInTheDocument();
    expect(within(screen.getByTestId('stat-failed')).getByText('1')).toBeInTheDocument();
    expect(within(screen.getByTestId('stat-waiting')).getByText('2')).toBeInTheDocument();
    expect(within(screen.getByTestId('stat-unknown')).getByText('1')).toBeInTheDocument();

    // recent activity entry
    expect(screen.getByText('Published job #101 to Target 1')).toBeInTheDocument();
  });

  it('hides the WAL badge when the database reports an unhealthy state', async () => {
    mockFetch({
      '/dashboard/overview': () => ({
        ...mockDashboard,
        telegram_connected: false,
        worker_alive: false,
        database_health: { ...mockDashboard.database_health, healthy: false, wal_enabled: false, journal_mode: 'delete' },
      }),
    });

    renderWithProviders(<DashboardPage />);

    expect(await screen.findByText('غير متصل بتيليجرام')).toBeInTheDocument();
    expect(screen.getByText('محرك المهام متوقف')).toBeInTheDocument();
    expect(screen.getByText('قاعدة البيانات تحتاج مراجعة')).toBeInTheDocument();
  });
});
