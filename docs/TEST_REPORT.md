# Telegram Auto Publisher — TEST REPORT

> نتائج **حقيقية** من تنفيذ فعلي (لا نتائج مُفترضة). جولة الإغلاق النهائية: **2026‑11‑06** · البيئة: Linux x86_64 · Python 3.13.16 · Node 20.20.2 · Chromium (headless) · nginx 1.26.3 · ffmpeg 7.1.5.
> إعادة التنفيذ: `pytest -q` · `npx vitest run` · `npm run build` · `node scripts/e2e_live_walkthrough.mjs <user> <pass>`

---

## 1. الملخص التنفيذي

| المجموعة | الأداة | الملفات | الاختبارات | النتيجة |
|---|---|---|---|---|
| Backend (unit/integration/DB/API/Telegram/publishing) | pytest 9 | 6 | **15** | ✅ `15 passed in 3.29s` (و`3.13s` في نسخة نظيفة) |
| Frontend (functional/UI wiring) | Vitest + Testing Library | 6 | **32** | ✅ `32 passed (9.66s)` |
| Build إنتاجي للواجهة | `tsc -b && vite build` | — | — | ✅ 0 أخطاء TypeScript |
| E2E حقيقي في متصفح (stack حيّ) | Playwright (Chromium) | 1 | **20 فحصًا** | ✅ `20/20 checks passed` |
| تثبيت من الصفر (نسخة نظيفة) | fresh clone + `pip install -r requirements.txt` | — | — | ✅ `15 passed in 3.13s` |
| فيديو عرض لوحة التحكم | Playwright + ffmpeg | 14 مشهدًا | — | ✅ `docs/media/dashboard_walkthrough.mp4` |
| تحقق إعدادات النشر | nginx -t · systemd-analyze · مخفّي الأسرار | — | — | ✅ كلها ناجحة (انظر §7) |
| OpenAPI | FastAPI | — | 40 مسارًا | ✅ موثّق في `/docs` |

**الإجمالي: 67 فحصًا آليًا ناجحًا (15 backend + 32 frontend + 20 E2E) — كلها أُعيد تشغيلها في جولة الإغلاق هذه بنفس النتائج.**

> ⚠️ **ما لم يُنفَّذ:** فحوص تيليجرام الحقيقية (حساب مصرّح + قنوات فعلية). هي **غير قابلة للتنفيذ من داخل هذه البيئة** لأنها تحتاج `api_id`/`api_hash` وهاتفك وOTP/2FA وقنواتك. التفاصيل والأدلة في `docs/LIVE_TELEGRAM_EVIDENCE.md`. نجاح الاختبارات أعلاه **لا يُعد** دليلًا على الربط الحقيقي بتيليجرام.

---

## 2. نتائج Backend (`pytest -q`)

```
15 passed, 1 warning in 3.29s
```
> التحذير الوحيد: `StarletteDeprecationWarning` من مكتبة starlette نفسها (لا علاقة بمنطق المشروع).

### `test_01_database_and_migrations.py` — Database & Migrations (4)
| الاختبار | يتحقق من |
|---|---|
| `test_sqlite_wal_foreign_keys_and_all_12_tables` | `journal_mode=wal`, `PRAGMA foreign_keys=ON`, وجود الـ12 جدولًا وكل الأعمدة المطلوبة |
| `test_foreign_key_and_unique_constraints_enforced` | انتهاك FK يُرفض؛ قيد `UNIQUE(source_channel_id, telegram_message_id)` يمنع الحدث المكرر؛ `UNIQUE(message_event_id, target_channel_id)` يمنع مهمة مكررة |
| `test_alembic_upgrade_and_downgrade_cycle` | `upgrade head → downgrade base → upgrade head` بلا أخطاء |
| `test_online_backup_checksum_and_verified_restore` | نسخة online أثناء التشغيل + SHA‑256 + استعادة تعيد البيانات بدقة |

### `test_02_auth_and_security.py` — Auth/Security (2)
- تسجيل دخول، إصدار JWT، RBAC (operator ممنوع من عمليات admin ⇒ 403)، تغيير كلمة المرور يُبطل الـJWT القديم.
- تشفير Fernet ثم فك التشفير، والتحقق من أن الـRedaction يخفي `password/code/api_hash/token/session` من السجلات.

### `test_03_telegram_connection.py` — Telegram Connection (1)
دورة كاملة عبر `FakeTelegramGateway`: `send_code → verify_code → AWAITING_PASSWORD → verify_password → CONNECTED → reconnect → logout`؛ والتأكد أن أي استجابة API **لا تحتوي** `api_hash` ولا الجلسة ولا الرمز.

### `test_04_e2e_all_12_scenarios.py` — السيناريوهات الاثنا عشر (3 اختبارات تغطي 12 سيناريو)
| # | السيناريو | النتيجة |
|---|---|---|
| 1 | مصدر واحد → وجهة واحدة | ✅ مهمة واحدة `PUBLISHED` |
| 2 | مصدر واحد → عدة وجهات | ✅ N مهمة مستقلة |
| 3 | عدة مصادر → وجهة واحدة | ✅ كل مصدر ينتج مهمته |
| 4 | عدة مصادر → عدة وجهات + **لا أرشيف ولا تعديلات** | ✅ الأحداث القديمة/المعدّلة لا تُنشئ مهامًا |
| 5 | وصول عدة منشورات متقاربة (burst) | ✅ لا فقدان ولا تكرار |
| 6 | انقطاع الاتصال ثم عودته | ✅ catch‑up للمرسائل الفائتة ضمن الحدود |
| 7 | إعادة تشغيل التطبيق ومهام موجودة | ✅ لا ازدواج، والمهام تُستكمل |
| 8 | فشل وجهة ونجاح أخرى | ✅ الناجحة `PUBLISHED` والفاشلة `FAILED` بلا إعادة نشر للناجحة |
| 9 | وصول ألبوم صور | ✅ تجميع `grouped_id` وترتيب العناصر و`target_message_ids` |
| 10 | وصول ملف/فيديو | ✅ نوع الوسيط و`caption` |
| 11 | منشور مكرر | ✅ يُرفض بقيد UNIQUE (`Duplicate event ignored`) |
| 12 | محتوى محمي / صلاحيات غير كافية + UNKNOWN | ✅ `SKIPPED` بسبب `noforwards`، فشل الصلاحيات `FAILED` بسبب حقيقي، ومهمة `UNKNOWN` تُعالَج بالمصالحة |

### `test_05_unit_formatter_and_recovery.py` — Unit & Recovery (3)
- **UTF‑16 entity shifting**: إضافة `prefix` إيموجي/عربي تُزيح offsets بدقة (يحاكي حد تيليجرام).
- **Exponential backoff**: النمو والحد الأقصى (`retry.max_seconds`).
- **Stale lock recovery**: مهمة `PROCESSING` بلا heartbeat ⇒ `UNKNOWN` (لا `QUEUED`) + `publish_attempts.outcome=UNKNOWN` + سبب مصالحة.

### `test_06_api_sources_targets_queue_settings.py` — REST API (2)
- دورة حياة المصادر/الوجهات + `verify` + `test-publish` + أخطاء الصلاحيات (`409` للتكرار، `404` لكيان مفقود).
- `/messages`, `/queue/jobs`, `retry`, `cancel`, `PUT /settings`, `integrity`, `backups` (إنشاء + قائمة + تنزيل + استعادة).

---

## 3. نتائج Frontend (`npx vitest run`)

```
Test Files  6 passed (6)
     Tests  32 passed (32)
  Duration  ~9.3s
```

| الملف | # | يتحقق من |
|---|---|---|
| `01_auth_and_api.test.tsx` | 4 | إرسال بيانات الدخول بالشكل الصحيح، تخزين JWT، إبراز خطأ 401، استخدام مسارات `/api/v1` النسبية + ترويسة Bearer، إبطال الجلسة عند 401 |
| `02_dashboard.test.tsx` | 2 | عرض كل المؤشرات من الاستجابة الحقيقية + حالة WAL/Worker، وإظهار التنبيه عند تعطل القاعدة |
| `03_sources_targets.test.tsx` | 5 | قائمة المصادر (baseline/last)، إنشاء مصدر (POST)، verify/start، شارات صلاحيات الوجهة، اختبار نشر يعرض رسالة تيليجرام الحقيقية |
| `04_routes.test.tsx` | 5 | عرض المسارات 1→1، toggle مستقل، **إنشاء N×M** (`/routes/bulk`)، حفظ كل حقول `route_filters`، حذف بتأكيد |
| `05_messages_queue.test.tsx` | 7 | سجل المنشورات + مهام كل وجهة، محتوى محمي `SKIPPED` بلا زر تجاوز، retry، تبويبات الطابور، **مصالحة UNKNOWN** (ترفض الإعادة العمياء)، إلغاء بتأكيد |
| `06_telegram_settings_i18n.test.tsx` | 9 | حالة الحساب بلا كشف أسرار، OTP ثم verify، reconnect، سلامة القاعدة، حفظ الإعدادات بأنواع صحيحة (number/boolean)، استعادة نسخة بتأكيد، التحقق من تطابق كلمة المرور، تصفية السجلات + درج JSON، **RTL عربي ↔ LTR إنجليزي** |

**Build:** `tsc -b && vite build` ⇒ `✓ 1600 modules transformed` · `dist/assets/index-*.js 322 kB (gzip 91.8 kB)` · 0 أخطاء.

---

## 4. نتائج E2E الحيّة (متصفح حقيقي ضد النظام العامل)

الحزمة: FastAPI على `:8000` + Worker + Vite على `:5173` + قاعدة SQLite حقيقية.
اللقطات محفوظة في `docs/screenshots/`.

```
PASS | Login page renders in Arabic RTL | dir=rtl
PASS | Invalid credentials rejected by real API | Invalid username or password.
PASS | Successful login → dashboard | /
PASS | JWT persisted for the session | eyJhbGciOiJI…
PASS | Telegram page shows auth state
PASS | Telegram page never leaks the API hash
PASS | Source created from the UI (persisted) | قناة تجريبية 1793913470977
PASS | Access verification surfaces the real backend reason
PASS | Target created from the UI (persisted) | وجهة تجريبية 1793913470977
PASS | N×M routes created atomically from the UI
PASS | Route filters saved through the API
PASS | Messages page loads from the API
PASS | Queue page filters by status tab
PASS | Audit logs list real operations (SOURCE|ROUTE|AUTH|BACKUP)
PASS | Integrity check reports WAL + FK state
PASS | Online backup created and listed
PASS | Language switch flips document direction to LTR | dir=ltr
PASS | Mobile drawer navigation opens on small screens
PASS | Protected route redirects to /login without a token
PASS | No unexpected browser console errors

=== LIVE E2E: 20/20 checks passed ===
```
> ملاحظة شفافية: الفحص الأول لخطأ الدخول يُنتج استجابة 401 مقصودة في console المتصفح، واستُثنيت من فحص "أخطاء console" لأنها سلوك متوقع ومطلوب.

### فحوص API مباشرة (curl) على النظام الحيّ
```
/api/v1/health            → status=ok, journal_mode=wal, 13 tables
/api/v1/dashboard/overview→ worker_alive=true, sources_total=…, routes_active=…
/api/v1/settings          → 8 مفاتيح نظام
/api/v1/settings/integrity→ healthy=true, wal=true, fk=true
POST /settings/backups    → tap_backup_20261105_205210_016428_smoke.db + SHA-256
/api/v1/telegram/status   → UNCONFIGURED (لم يُربط حساب بعد) — بدون أسرار
/api/v1/logs              → BACKUP_CREATED, LOGIN_SUCCESS, WORKER_STARTED
POST /routes/bulk         → إنشاء مسارات N×M + الفلاتر محفوظة
POST /sources/1/verify    → accessible=false + سبب صريح (الحساب غير متصل)
```

---

## 5. مصفوفة التغطية (المتطلبات ← الاختبارات)

| المتطلب | اختبار Backend | اختبار Frontend | E2E |
|---|---|---|---|
| ربط الحساب OTP/2FA | `test_03` | `06` | ✅ صفحة الحساب |
| عدم كشف الجلسة/الأسرار | `test_02`, `test_03` | `06` | ✅ |
| المصادر + baseline | `test_06`, `test_04` | `03` | ✅ |
| الوجهات + صلاحيات | `test_06` | `03` | ✅ |
| المسارات 1→1/1→N/N→1/N→N | `test_04` | `04` | ✅ |
| route_filters (كل الحقول) | `test_04` | `04` | ✅ |
| لا أرشيف / لا تعديلات | `test_04` (سيناريو 4) | — | — |
| الألبومات | `test_04` (9) | — | — |
| الوسائط (ملف/فيديو) | `test_04` (10) | — | — |
| منع التكرار | `test_01`, `test_04` (11) | — | — |
| فشل وجهة ≠ إعادة نشر | `test_04` (8) | `05` | — |
| UNKNOWN + مصالحة | `test_05`, `test_04` (12) | `05` | — |
| الحماية noforwards ⇒ SKIPPED | `test_04` (12) | `05` | — |
| WAL/FK/ترحيلات/نسخ | `test_01` | `06` | ✅ |
| RBAC/JWT/Argon2id | `test_02` | `01` | ✅ |
| i18n و RTL | — | `06` | ✅ |
| الاستجابة للهاتف | — | — | ✅ |

---

## 6. القيود المعروفة (Known Limitations)

1. **Exactly‑Once مطلق غير مضمون** (تيليجرام لا يوفّره). التخفيف: حالات `UNKNOWN` + مصالحة قبل الإعادة.
2. **اختبار حساب Telegram حقيقي**: الآلي يستخدم `FakeTelegramGateway` (حتمي، لا شبكة). الاختبار العملي على حساب وقنوات مصرّح بها يتطلب API ID/Hash + OTP منك (خطواته في `USER_GUIDE.md` §0). الشيفرة الحقيقية موجودة في `telegram/gateway.py` ولم تُستبدل بأي mock في الإنتاج.
3. **لا استيراد أرشيف** ولا **نشر للتعديلات/الحذف** (قرار المتطلب).
4. **SQLite**: worker واحد + خادم واحد؛ التوسّع الأفقي يتطلب PostgreSQL + طابور موزّع (موثّق في TDD ADR‑001/002).
5. **حدود تيليجرام**: FloodWait وحجم الوسائط تُعالَج كأخطاء قابلة للإعادة أو `FAILED` مع السبب.
6. **Frontend tests** تستخدم fetch مُحاكى يطابق عقود الـAPI الحقيقية (`/api/v1/...`)، بينما E2E يتحقق من التكامل الحقيقي في متصفح — لا mock في مسار E2E.

---

## 7. جولة الإغلاق النهائي — أدلة قابلة لإعادة التشغيل (2026‑11‑06)

هذه الجولة أُعيد فيها كل ما سبق **من الصفر**، وأُضيفت أدلة جديدة. المخرجات الخام محفوظة في `docs/evidence/`.

| # | الأمر | النتيجة | الملف |
|---|---|---|---|
| 1 | `pip install -r backend/requirements.txt` في venv جديد | 47 حزمة · `pip check` نظيف | `docs/evidence/01_clean_dependency_install.txt` |
| 2 | `bash scripts/ci/prove_clean_install.sh` | تثبيت نظيف كامل: ترحيلات + 13 جدولًا + بذرة المشرف + `15 passed in 3.47s` | `docs/evidence/02_clean_clone_install.txt` |
| 3 | `bash scripts/ci/prove_nginx_proxy.sh` | nginx 1.26.3: SPA 200، deep link 200، assets 200، `Cache-Control` واحد، 4 رؤوس أمان، 40 مسارًا عبر proxy، تسجيل دخول وداشبورد عبر nginx | `docs/evidence/03_nginx_proxy_proof.txt` |
| 4 | `bash scripts/ci/validate_systemd.sh` | 4 وحدات (backend/worker/backup + timer) صحيحة التحميل | `docs/evidence/04_systemd_validation.txt` |
| 5 | `python3 scripts/ci/scan_secrets.py` | نظيف — 164 ملفًا متتبعًا، 7 أنماط | `docs/evidence/05_secret_scan.txt` |
| 6 | `python3 scripts/live_telegram_e2e.py --dry-run` | 2 PASS (دخول + عدم تسريب الأسرار) · 6 FAIL = متطلبات تيليجرام الناقصة | `docs/evidence/06_live_telegram_prerequisites.txt` |
| 7 | `node scripts/record_dashboard_video.mjs` | فيديو 63 ثانية + 14 مشهدًا + ترجمة SRT مدمجة | `docs/media/dashboard_walkthrough.{mp4,webm,srt}` |

### إصلاحات كشفها التشغيل النظيف (وليس التخمين)

| المشكلة | كيف ظهرت | الإصلاح |
|---|---|---|
| `PermissionError: /opt/tap/runtime` | فشل `alembic upgrade` في نسخة نظيفة | `.env.example` صار نسبيًا `./runtime/…`، و`config.py` يحلّ المسارات نسبةً لجذر المشروع |
| Alembic ينشئ قاعدة بيانات في `backend/runtime/` | `sqlite:///./runtime/tap.db` يُحلّ نسبةً لـCWD | `resolve_database_url` + `resolved_database_path()` |
| مولّد الأسرار لا يطابق بدائل `.env.example` | `Fernet key must be 32 bytes` | `scripts/ci/generate_env_secrets.py` |
| `asyncio.run(init_database())` | `a coroutine was expected, got None` | الدالة متزامنة — صُحّح الاستدعاء في السكربت والوثائق |
| `TAP_ADMIN_PASSWORD is required` بلا جرد | تشغيل dry-run بلا مخرجات مفيدة | السكربت يقرأ `.env` ويطبع جردًا لكل متطلب |
| `NameError: prefix` / `PermissionError` في سكربت nginx | تشغيل فعلي | إصلاح f-string والكتابة عبر `sudo python3` |

### ما لم يُنفَّذ في هذه الجولة

البند 1→7 (تيليجرام حقيقي). غير قابل للتنفيذ من داخل بيئة الإغلاق: يحتاج `api_id/hash` من حسابك، رمز OTP على جهازك، كلمة مرور 2FA، وقنوات حقيقية. التفاصيل الكاملة والخطوات في `docs/LIVE_TELEGRAM_EVIDENCE.md`، والحكم النهائي في `docs/PRODUCTION_CLOSURE.md`.
