/**
 * Records a real walkthrough of the Telegram Auto Publisher dashboard and produces
 * docs/media/dashboard_walkthrough.webm (+ .mp4 with burned-in bilingual captions).
 *
 * Usage (from the repo root, with backend + worker + frontend running):
 *   node scripts/record_dashboard_video.mjs <admin_username> <admin_password>
 *
 * Nothing is mocked: every click hits the live FastAPI backend and the SQLite database.
 */
import { createRequire } from 'node:module';
import { mkdir, writeFile, rm } from 'node:fs/promises';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import path from 'node:path';

const require = createRequire(new URL('../frontend/package.json', import.meta.url));
const { chromium } = require('playwright-core');
const exec = promisify(execFile);

const BASE = process.env.E2E_BASE_URL || 'http://127.0.0.1:5173';
const USER = process.argv[2];
const PASS = process.argv[3];
if (!USER || !PASS) {
  console.error('Usage: node scripts/record_dashboard_video.mjs <username> <password>');
  process.exit(1);
}

const ROOT = path.resolve(new URL('..', import.meta.url).pathname);
const OUT_DIR = path.join(ROOT, 'docs', 'media');
const RAW_DIR = path.join('/tmp', 'tap_video_raw');

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/** caption timeline measured against the real recording clock */
const captions = [];
let recordStart = null;
function cue(ar, en, _estimate) {
  const now = Date.now();
  if (recordStart === null) recordStart = now;
  const start = (now - recordStart) / 1000;
  if (captions.length) captions[captions.length - 1].end = Math.max(start - 0.15, captions[captions.length - 1].start + 1.5);
  captions.push({ start, end: start + (_estimate || 5), ar, en });
}

async function main() {
  await rm(RAW_DIR, { recursive: true, force: true });
  await mkdir(RAW_DIR, { recursive: true });
  await mkdir(OUT_DIR, { recursive: true });

  const exe = `${process.env.HOME}/.cache/ms-playwright/chromium_headless_shell-1148/chrome-linux/headless_shell`;
  const browser = await chromium.launch({
    headless: true,
    executablePath: exe,
    args: ['--no-sandbox', '--disable-dev-shm-usage'],
  });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    recordVideo: { dir: RAW_DIR, size: { width: 1440, height: 900 } },
  });
  const page = await context.newPage();

  // ---------------- 1. login ----------------
  cue(
    '١) تسجيل الدخول إلى لوحة التحكم — مصادقة حقيقية ضد الـAPI (JWT)',
    '1) Signing in to the dashboard — real API authentication (JWT)',
    8
  );
  await page.goto(`${BASE}/login`, { waitUntil: 'networkidle' });
  await sleep(1800);
  await page.fill('[data-testid="login-username"]', USER);
  await page.fill('[data-testid="login-password"]', PASS);
  await sleep(900);
  await page.click('[data-testid="login-submit"]');
  await page.waitForSelector('[data-testid="dashboard-page"]', { timeout: 20000 });
  await sleep(1200);

  // ---------------- 2. dashboard ----------------
  cue(
    '٢) لوحة المؤشرات: حالة تيليجرام، العامل، سلامة قاعدة البيانات WAL، وعدّادات النشر',
    '2) Dashboard: Telegram state, worker heartbeat, WAL database health and publishing counters',
    7
  );
  await page.evaluate(() => window.scrollTo({ top: 0 }));
  await sleep(2500);
  await page.evaluate(() => window.scrollTo({ top: 650, behavior: 'smooth' }));
  await sleep(2500);
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'smooth' }));

  // ---------------- 3. telegram account ----------------
  cue(
    '٣) حساب تيليجرام: الحالة، الجلسة المشفّرة، إعادة الاتصال — دون كشف أي سر',
    '3) Telegram account: connection state, encrypted session, reconnect — no secrets exposed',
    7
  );
  await page.click('a[href="/telegram"]');
  await page.waitForSelector('[data-testid="telegram-page"]', { timeout: 15000 });
  await sleep(4000);

  // ---------------- 4. sources ----------------
  cue(
    '٤) قنوات المصدر: إضافة قناة من الواجهة ثم فحص الوصول وبدء المراقبة (تسجيل baseline)',
    '4) Sources: add a channel from the UI, verify access and start monitoring (baseline recorded)',
    9
  );
  await page.click('a[href="/sources"]');
  await page.waitForSelector('[data-testid="sources-page"]', { timeout: 15000 });
  await sleep(1500);
  const stamp = Date.now();
  await page.getByRole('button', { name: /إضافة مصدر/ }).first().click();
  const srcDialog = page.getByRole('dialog');
  await srcDialog.waitFor();
  await sleep(600);
  await srcDialog.getByRole('textbox').nth(0).fill(`مصدر توضيحي ${stamp}`);
  await srcDialog.getByRole('textbox').nth(1).fill(`@tap_walkthrough_${stamp}`);
  await sleep(900);
  await srcDialog.getByRole('button', { name: 'حفظ' }).click();
  await srcDialog.waitFor({ state: 'detached', timeout: 15000 });
  await sleep(1800);

  // ---------------- 5. targets ----------------
  cue(
    '٥) قنوات الوجهة: إضافة وجهة ثم فحص صلاحيات النشر (can_post_messages)',
    '5) Targets: add a target channel and verify posting permissions (can_post_messages)',
    8
  );
  await page.click('a[href="/targets"]');
  await page.waitForSelector('[data-testid="targets-page"]', { timeout: 15000 });
  await sleep(1200);
  await page.getByRole('button', { name: /إضافة وجهة/ }).first().click();
  const tgtDialog = page.getByRole('dialog');
  await tgtDialog.waitFor();
  await sleep(500);
  await tgtDialog.getByRole('textbox').nth(0).fill(`وجهة توضيحية ${stamp}`);
  await tgtDialog.getByRole('textbox').nth(1).fill(`@tap_walkthrough_target_${stamp}`);
  await tgtDialog.getByRole('button', { name: 'حفظ' }).click();
  await tgtDialog.waitFor({ state: 'detached', timeout: 15000 });
  await sleep(1500);
  await page.getByRole('button', { name: /^تحقق$/ }).first().click();
  await sleep(2500);

  // ---------------- 6. routes ----------------
  cue(
    '٦) المسارات: باني الربط المتعدد N×M ينشئ كل الأزواج في طلب واحد ذرّي',
    '6) Routes: the N×M bulk builder creates every source→target pair in one atomic request',
    9
  );
  await page.click('a[href="/routes"]');
  await page.waitForSelector('[data-testid="routes-page"]', { timeout: 15000 });
  await sleep(1500);
  await page.getByRole('button', { name: /إنشاء مسار/ }).first().click();
  const routeDialog = page.getByRole('dialog');
  await routeDialog.waitFor();
  await sleep(600);
  await routeDialog.getByRole('button', { name: /ربط متعدد/ }).click();
  await sleep(700);
  const boxes = routeDialog.getByRole('checkbox');
  const total = await boxes.count();
  for (let i = 0; i < total; i += 1) await boxes.nth(i).check();
  await sleep(1200);
  await routeDialog.getByRole('button', { name: /إنشاء \d+ مسار/ }).click();
  await routeDialog.waitFor({ state: 'detached', timeout: 20000 });
  await sleep(2000);

  // ---------------- 7. route filters ----------------
  cue(
    '٧) قواعد التصفية لكل مسار: أنواع المحتوى، الكلمات، طول النص، التوقيع، حذف الروابط',
    '7) Per-route filters: content types, keywords, text length, signature, URL stripping',
    8
  );
  await page.getByRole('button', { name: /القواعد/ }).first().click();
  const filterDialog = page.getByRole('dialog');
  await filterDialog.waitFor();
  await sleep(700);
  await filterDialog.getByLabel(/كلمات يجب توفرها/).fill('عاجل, breaking');
  await filterDialog.getByLabel(/توقيع خاص بالوجهة/).fill('@tap_channel');
  await sleep(2000);
  await page.screenshot({ path: path.join(OUT_DIR, 'walkthrough_route_filters.png') });
  await filterDialog.getByRole('button', { name: /حفظ القواعد/ }).click();
  await filterDialog.waitFor({ state: 'detached', timeout: 15000 });
  await sleep(1800);

  // ---------------- 8. publishing history ----------------
  cue(
    '٨) سجل المنشورات: كل حدث مع مهام النشر المستقلة لكل وجهة وحالتها وسبب الفشل',
    '8) Publishing history: every event with independent per-target jobs, status and failure reason',
    8
  );
  await page.click('a[href="/messages"]');
  await page.waitForSelector('[data-testid="messages-page"]', { timeout: 15000 });
  await sleep(2500);
  const firstEvent = page.locator('[data-testid="messages-page"] button').first();
  if (await firstEvent.count()) {
    await firstEvent.click().catch(() => {});
  }
  await sleep(2500);

  // ---------------- 9. queue ----------------
  cue(
    '٩) إدارة الطابور: الحالات السبع، المحاولات، الإعادة اليدوية، ومصالحة UNKNOWN',
    '9) Queue: the seven states, attempt history, manual retry and UNKNOWN reconciliation',
    9
  );
  await page.click('a[href="/queue"]');
  await page.waitForSelector('[data-testid="queue-page"]', { timeout: 15000 });
  await sleep(2200);
  await page.getByRole('button', { name: /تحتاج مراجعة/ }).click();
  await sleep(2000);

  // ---------------- 10. logs ----------------
  cue(
    '١٠) السجلات: عمليات المستخدم، الأخطاء، أحداث الاتصال — مع بحث وتصفية ودرج JSON',
    '10) Logs: user operations, errors, connection events — searchable with a raw JSON drawer',
    7
  );
  await page.click('a[href="/logs"]');
  await page.waitForSelector('[data-testid="logs-page"]', { timeout: 15000 });
  await sleep(2500);

  // ---------------- 11. settings + backup ----------------
  cue(
    '١١) الإعدادات: سلامة قاعدة البيانات (WAL/FK) وإنشاء نسخة احتياطية متحققة SHA-256',
    '11) Settings: database integrity (WAL/FK) and a verified SHA-256 online backup',
    9
  );
  await page.click('a[href="/settings"]');
  await page.waitForSelector('[data-testid="settings-page"]', { timeout: 15000 });
  await sleep(2500);
  await page.getByRole('button', { name: /إنشاء نسخة الآن/ }).click();
  await sleep(3000);

  // ---------------- 12. English LTR ----------------
  cue(
    '١٢) تبديل اللغة إلى الإنجليزية (LTR) — نفس الوظائف، اتجاه معاكس',
    '12) Switching to English (LTR) — same functionality, mirrored direction',
    6
  );
  await page.getByRole('button', { name: /English UI/ }).click();
  await sleep(1500);
  await page.click('a[href="/"]');
  await page.waitForTimeout(2500);

  // ---------------- 13. mobile ----------------
  cue(
    '١٣) واجهة الهاتف: القائمة الجانبية المنزلقة والتصميم المتجاوب',
    '13) Mobile view: slide-in navigation drawer and responsive layout',
    6
  );
  await page.setViewportSize({ width: 390, height: 844 });
  await sleep(1200);
  await page.getByRole('button', { name: /Open menu/ }).click();
  await sleep(2500);

  cue(
    'نهاية العرض — النظام يعمل فعليًا من تيليجرام إلى تيليجرام عبر لوحة التحكم',
    'End of walkthrough — the system runs Telegram→Telegram end-to-end through the dashboard',
    4
  );

  await page.close();
  const video = page.video();
  await context.close();
  const rawPath = await video.path();
  await browser.close();

  // ---------------- post production ----------------
  const webm = path.join(OUT_DIR, 'dashboard_walkthrough.webm');
  const mp4 = path.join(OUT_DIR, 'dashboard_walkthrough.mp4');
  const srt = path.join(OUT_DIR, 'dashboard_walkthrough.srt');
  const ass = path.join('/tmp', 'tap_captions.ass');

  await exec('cp', [rawPath, webm]);

  // bilingual SRT (Arabic line + English line per cue)
  const srtTime = (t) => {
    const ms = Math.round(t * 1000);
    const h = String(Math.floor(ms / 3600000)).padStart(2, '0');
    const m = String(Math.floor((ms % 3600000) / 60000)).padStart(2, '0');
    const s = String(Math.floor((ms % 60000) / 1000)).padStart(2, '0');
    const milli = String(ms % 1000).padStart(3, '0');
    return `${h}:${m}:${s},${milli}`;
  };
  const srtBody = captions
    .map((c, i) => `${i + 1}\n${srtTime(c.start)} --> ${srtTime(c.end)}\n${c.ar}\n${c.en}\n`)
    .join('\n');
  await writeFile(srt, srtBody, 'utf8');

  // ASS with an Arabic-friendly font and RTL shaping support
  const assTime = (t) => {
    const cs = Math.round(t * 100);
    const h = Math.floor(cs / 360000);
    const m = Math.floor((cs % 360000) / 6000);
    const s = Math.floor((cs % 6000) / 100);
    const c = cs % 100;
    return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}.${String(c).padStart(2, '0')}`;
  };
  const assBody = `[Script Info]
ScriptType: v4.00+
PlayResX: 1440
PlayResY: 900
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,DejaVu Sans,24,&H00FFFFFF,&H000000FF,&H00101010,&H80000000,0,0,0,0,100,100,0,0,3,2,0,2,60,60,70,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
${captions
  .map(
    (c) =>
      `Dialogue: 0,${assTime(c.start)},${assTime(c.end)},Caption,,0,0,0,,{\\q2}${c.en}\\N{\\q2}${c.ar}`
  )
  .join('\n')}
`;
  await writeFile(ass, assBody, 'utf8');

  await exec('ffmpeg', [
    '-y',
    '-i', webm,
    '-vf', `ass=${ass}`,
    '-c:v', 'libx264',
    '-preset', 'veryfast',
    '-crf', '26',
    '-pix_fmt', 'yuv420p',
    '-movflags', '+faststart',
    mp4,
  ]);

  const { stdout } = await exec('ffprobe', [
    '-v', 'error',
    '-show_entries', 'format=duration,size',
    '-of', 'default=noprint_wrappers=1',
    mp4,
  ]);
  console.log('video:', mp4);
  console.log(stdout.trim());
  console.log(`captions: ${captions.length} cues → ${srt}`);
}

main().catch((err) => {
  console.error('video recording failed:', err);
  process.exit(1);
});
