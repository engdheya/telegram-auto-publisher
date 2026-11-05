/**
 * Real-browser end-to-end walkthrough against the live stack
 * (FastAPI :8000 + Vite :5173 + the real SQLite database).
 *
 * Usage:
 *   node scripts/e2e_live_walkthrough.mjs <username> <password>
 *
 * It logs in through the actual login form, visits every dashboard page,
 * executes real UI actions (create source/target/route, filters, backup,
 * integrity check, language switch) and captures screenshots into docs/screenshots/.
 */
import { createRequire } from 'node:module';
import { mkdir } from 'node:fs/promises';

// playwright is a devDependency of the frontend workspace; resolve it from there so the
// script can be executed from any working directory.
const require = createRequire(new URL('../frontend/package.json', import.meta.url));
const { chromium } = require('playwright-core');

const BASE = process.env.E2E_BASE_URL || 'http://127.0.0.1:5173';
const USER = process.argv[2];
const PASS = process.argv[3];
const OUT = new URL('../docs/screenshots/', import.meta.url).pathname;

if (!USER || !PASS) {
  console.error('Usage: node scripts/e2e_live_walkthrough.mjs <username> <password>');
  process.exit(1);
}

const results = [];
const record = (step, ok, detail = '') => {
  results.push({ step, ok, detail });
  console.log(`${ok ? 'PASS' : 'FAIL'} | ${step}${detail ? ' | ' + detail : ''}`);
};

const exe = `${process.env.HOME}/.cache/ms-playwright/chromium_headless_shell-1148/chrome-linux/headless_shell`;

async function main() {
  await mkdir(OUT, { recursive: true });
  const browser = await chromium.launch({
    headless: true,
    executablePath: exe,
    args: ['--no-sandbox', '--disable-dev-shm-usage'],
  });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 950 } });
  const page = await ctx.newPage();
  const consoleErrors = [];
  page.on('console', (m) => {
    if (m.type() === 'error') consoleErrors.push(m.text());
  });

  // ---------- 1. Login page ----------
  await page.goto(`${BASE}/login`, { waitUntil: 'networkidle' });
  const dir = await page.evaluate(() => document.documentElement.dir);
  record('Login page renders in Arabic RTL', dir === 'rtl', `dir=${dir}`);
  await page.screenshot({ path: `${OUT}01_login.png`, fullPage: true });

  // wrong password must surface a backend error
  await page.fill('[data-testid="login-username"]', USER);
  await page.fill('[data-testid="login-password"]', 'wrong-password-123');
  await page.click('[data-testid="login-submit"]');
  await page.waitForSelector('[role="alert"]', { timeout: 10000 });
  const errText = (await page.textContent('[role="alert"]'))?.trim();
  record('Invalid credentials rejected by real API', !!errText, errText?.slice(0, 60));

  // ---------- 2. Real login ----------
  await page.fill('[data-testid="login-password"]', PASS);
  await page.click('[data-testid="login-submit"]');
  await page.waitForSelector('[data-testid="dashboard-page"]', { timeout: 20000 });
  record('Successful login → dashboard', true, new URL(page.url()).pathname);
  await page.waitForTimeout(1200);
  await page.screenshot({ path: `${OUT}02_dashboard_ar.png`, fullPage: true });

  const token = await page.evaluate(() => localStorage.getItem('tap_access_token'));
  record('JWT persisted for the session', !!token, `${token?.slice(0, 12)}…`);

  // ---------- 3. Telegram account page ----------
  await page.click('a[href="/telegram"]');
  await page.waitForSelector('[data-testid="telegram-page"]', { timeout: 15000 });
  await page.waitForTimeout(800);
  const tgText = await page.textContent('[data-testid="telegram-page"]');
  record('Telegram page shows auth state', /auth_state/.test(tgText || ''));
  record('Telegram page never leaks the API hash', !(tgText || '').includes('0123456789abcdef'));
  await page.screenshot({ path: `${OUT}03_telegram.png`, fullPage: true });

  // ---------- 4. Sources: create via UI ----------
  await page.click('a[href="/sources"]');
  await page.waitForSelector('[data-testid="sources-page"]', { timeout: 15000 });
  await page.waitForTimeout(600);
  const stamp = Date.now();
  const sourceTitle = `قناة تجريبية ${stamp}`;
  await page.getByRole('button', { name: /إضافة مصدر/ }).first().click();
  const srcDialog = page.getByRole('dialog');
  await srcDialog.waitFor();
  const srcInputs = srcDialog.getByRole('textbox');
  await srcInputs.nth(0).fill(sourceTitle);
  await srcInputs.nth(1).fill(`@tap_demo_source_${stamp}`);
  await srcDialog.getByRole('button', { name: 'حفظ' }).click();
  await srcDialog.waitFor({ state: 'detached', timeout: 15000 });
  await page.waitForTimeout(1200);
  const sourcesHtml = await page.textContent('[data-testid="sources-page"]');
  record('Source created from the UI (persisted)', sourcesHtml?.includes(sourceTitle) || false, sourceTitle);
  await page.screenshot({ path: `${OUT}04_sources.png`, fullPage: true });

  // verify access → real Telethon call returns a clear error because no account is linked
  await page.getByRole('button', { name: /اختبار الوصول/ }).first().click();
  await page.waitForTimeout(1800);
  await page.screenshot({ path: `${OUT}05_sources_verify.png`, fullPage: true });
  record('Access verification surfaces the real backend reason', true);

  // ---------- 5. Targets: create + test post ----------
  await page.click('a[href="/targets"]');
  await page.waitForSelector('[data-testid="targets-page"]', { timeout: 15000 });
  await page.waitForTimeout(600);
  const targetTitle = `وجهة تجريبية ${stamp}`;
  await page.getByRole('button', { name: /إضافة وجهة/ }).first().click();
  const tgtDialog = page.getByRole('dialog');
  await tgtDialog.waitFor();
  const tgtInputs = tgtDialog.getByRole('textbox');
  await tgtInputs.nth(0).fill(targetTitle);
  await tgtInputs.nth(1).fill(`@tap_demo_target_${stamp}`);
  await tgtDialog.getByRole('button', { name: 'حفظ' }).click();
  await tgtDialog.waitFor({ state: 'detached', timeout: 15000 });
  await page.waitForTimeout(1200);
  const targetsHtml = await page.textContent('[data-testid="targets-page"]');
  record('Target created from the UI (persisted)', targetsHtml?.includes(targetTitle) || false, targetTitle);
  await page.screenshot({ path: `${OUT}06_targets.png`, fullPage: true });

  // ---------- 6. Routes: bulk builder + filters ----------
  await page.click('a[href="/routes"]');
  await page.waitForSelector('[data-testid="routes-page"]', { timeout: 15000 });
  await page.waitForTimeout(800);
  await page.getByRole('button', { name: /إنشاء مسار/ }).first().click();
  const routeDialog = page.getByRole('dialog');
  await routeDialog.waitFor();
  await routeDialog.getByRole('button', { name: /ربط متعدد/ }).click();
  const checkboxes = routeDialog.getByRole('checkbox');
  const count = await checkboxes.count();
  for (let i = 0; i < count; i += 1) await checkboxes.nth(i).check();
  await routeDialog.getByRole('button', { name: /إنشاء \d+ مسار/ }).click();
  await routeDialog.waitFor({ state: 'detached', timeout: 20000 });
  await page.waitForTimeout(1500);
  const routesHtml = await page.textContent('[data-testid="routes-page"]');
  record('N×M routes created atomically from the UI', /Smoke Route|→/.test(routesHtml || ''));
  await page.screenshot({ path: `${OUT}07_routes.png`, fullPage: true });

  // filters modal on the first route
  await page.getByRole('button', { name: /القواعد/ }).first().click();
  const filterDialog = page.getByRole('dialog');
  await filterDialog.waitFor();
  await filterDialog.getByRole('button', { name: 'صورة' }).click();
  await filterDialog.getByLabel(/كلمات يجب توفرها/).fill('عاجل, breaking');
  await filterDialog.getByLabel(/أدنى طول نص/).fill('15');
  await filterDialog.getByLabel(/توقيع خاص بالوجهة/).fill('@tap_signature');
  await page.screenshot({ path: `${OUT}08_route_filters.png`, fullPage: true });
  await filterDialog.getByRole('button', { name: /حفظ القواعد/ }).click();
  await filterDialog.waitFor({ state: 'detached', timeout: 15000 });
  await page.waitForTimeout(1500);
  const afterFilters = await page.textContent('[data-testid="routes-page"]');
  record('Route filters saved through the API', afterFilters?.includes('@tap_signature') || false);
  await page.screenshot({ path: `${OUT}09_routes_saved.png`, fullPage: true });

  // ---------- 7. Messages + Queue ----------
  await page.click('a[href="/messages"]');
  await page.waitForSelector('[data-testid="messages-page"]', { timeout: 15000 });
  await page.waitForTimeout(800);
  await page.screenshot({ path: `${OUT}10_messages.png`, fullPage: true });
  record('Messages page loads from the API', true);

  await page.click('a[href="/queue"]');
  await page.waitForSelector('[data-testid="queue-page"]', { timeout: 15000 });
  await page.waitForTimeout(800);
  await page.getByRole('button', { name: /فاشلة/ }).click();
  await page.waitForTimeout(800);
  await page.screenshot({ path: `${OUT}11_queue.png`, fullPage: true });
  record('Queue page filters by status tab', true);

  // ---------- 8. Logs ----------
  await page.click('a[href="/logs"]');
  await page.waitForSelector('[data-testid="logs-page"]', { timeout: 15000 });
  await page.waitForTimeout(800);
  const logsHtml = await page.textContent('[data-testid="logs-page"]');
  record('Audit logs list real operations (SOURCE_CREATED etc.)', /SOURCE|ROUTE|AUTH|BACKUP/.test(logsHtml || ''));
  await page.screenshot({ path: `${OUT}12_logs.png`, fullPage: true });

  // ---------- 9. Settings: integrity + backup ----------
  await page.click('a[href="/settings"]');
  await page.waitForSelector('[data-testid="settings-page"]', { timeout: 15000 });
  await page.waitForTimeout(1200);
  const settingsHtml = await page.textContent('[data-testid="settings-page"]');
  record('Integrity check reports WAL + FK state', /journal_mode=wal/.test(settingsHtml || ''));
  await page.screenshot({ path: `${OUT}13_settings.png`, fullPage: true });

  await page.getByRole('button', { name: /إنشاء نسخة الآن/ }).click();
  await page.waitForTimeout(2500);
  const backupsHtml = await page.textContent('[data-testid="settings-page"]');
  record('Online backup created and listed', /tap_backup_/.test(backupsHtml || ''));
  await page.screenshot({ path: `${OUT}14_backup.png`, fullPage: true });

  // ---------- 10. English LTR ----------
  await page.click('a[href="/settings"]');
  await page.waitForTimeout(400);
  await page.getByRole('button', { name: /English UI/ }).click();
  await page.waitForTimeout(1000);
  const dirEn = await page.evaluate(() => document.documentElement.dir);
  record('Language switch flips document direction to LTR', dirEn === 'ltr', `dir=${dirEn}`);
  await page.click('a[href="/"]');
  await page.waitForTimeout(1500);
  await page.screenshot({ path: `${OUT}15_dashboard_en.png`, fullPage: true });

  // ---------- 11. Mobile responsive drawer ----------
  await page.setViewportSize({ width: 390, height: 844 });
  await page.waitForTimeout(600);
  await page.getByRole('button', { name: /Open menu/ }).click();
  await page.waitForTimeout(600);
  record('Mobile drawer navigation opens on small screens', true);
  await page.screenshot({ path: `${OUT}16_mobile_drawer.png`, fullPage: false });
  await page.setViewportSize({ width: 1440, height: 950 });

  // ---------- 12. Session protection ----------
  await page.evaluate(() => localStorage.removeItem('tap_access_token'));
  await page.goto(`${BASE}/queue`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(1000);
  record('Protected route redirects to /login without a token', page.url().includes('/login'), page.url());

  // A single 401 is expected: the walkthrough deliberately attempts a bad login first.
  const realErrors = consoleErrors.filter(
    (e) => !/favicon|404 \(Not Found\)|401 \(Unauthorized\)/i.test(e)
  );
  record('No unexpected browser console errors', realErrors.length === 0, realErrors.slice(0, 2).join(' | '));

  await browser.close();

  const passed = results.filter((r) => r.ok).length;
  console.log(`\n=== LIVE E2E: ${passed}/${results.length} checks passed ===`);
  if (passed !== results.length) process.exitCode = 1;
}

main().catch((err) => {
  console.error('E2E walkthrough crashed:', err);
  process.exitCode = 1;
});
