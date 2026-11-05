# Telegram Auto Publisher — TDD (Technical Design Document)

> Version 1.0.0 · Architecture, data flow, and every consequential engineering decision.

---

## 1. نظرة عامة على المعمارية (Architecture Overview)

```
                         ┌──────────────────────────────────────────┐
                         │      React 18 + TS + Tailwind (SPA)      │
                         │   10 pages · AR/EN · RTL/LTR · responsive│
                         └───────────────┬──────────────────────────┘
                                         │ HTTPS · JWT Bearer
                                         │ /api/v1/*  (relative URLs only)
                         ┌───────────────▼──────────────────────────┐
                         │        Nginx (TLS, static, reverse proxy) │
                         └───────────────┬──────────────────────────┘
                                         │ http://127.0.0.1:8000
   ┌─────────────────────────────────────▼─────────────────────────────────────┐
   │                        FastAPI application (uvicorn)                       │
   │  api/deps.py (JWT, RBAC) · endpoints/{auth,dashboard,telegram,sources,     │
   │  targets,routes,messages,queue,logs,settings}.py · OpenAPI at /docs        │
   └───────────────┬───────────────────────────────────────────┬───────────────┘
                   │ SQLAlchemy 2.x (sync)                     │
   ┌───────────────▼──────────────┐              ┌─────────────▼──────────────┐
   │  services/                   │              │  telegram/                 │
   │  · telegram_service          │              │  · gateway (Telethon mgr)  │
   │  · ingestion_service         │              │  · listener (NewMessage)   │
   │  · filter_engine             │              │  · formatter (UTF-16       │
   │  · publishing_engine         │              │    entity shifting)        │
   │  · ReconciliationService     │              └─────────────┬──────────────┘
   └───────────────┬──────────────┘                            │ MTProto
                   │                                           ▼
   ┌───────────────▼──────────────┐                    ┌─────────────────┐
   │  workers/runner.py           │                    │ Telegram servers │
   │  WorkerOrchestrator:         │                    │ (accounts/chats) │
   │  · queue publisher loop      │                    └─────────────────┘
   │  · album flusher loop        │
   │  · watchdog / stale recovery │
   └───────────────┬──────────────┘
                   │
   ┌───────────────▼───────────────────────────────────────────────────────────┐
   │   SQLite (WAL) · runtime/tap.db · SQLAlchemy models · Alembic migrations   │
   │   12 app tables: users, telegram_accounts, source_channels,               │
   │   target_channels, publishing_routes, route_filters, message_events,       │
   │   message_media, publish_jobs, publish_attempts, audit_logs,              │
   │   system_settings  (+ alembic_version ⇒ 13 rows in sqlite_master)         │
   └───────────────────────────────────────────────────────────────────────────┘
```

**Processing topology:** the HTTP API and the worker are **separate processes** sharing one SQLite file. The API never publishes to Telegram on the request path (except explicit `test-publish`/`reconnect`/`verify` actions), which keeps request latency independent from Telegram network behaviour. Exactly **one worker process** must run per database (documented and enforced by convention + systemd).

---

## 2. هيكل المشروع (Project Structure)

```
telegram-auto-publisher/
├── backend/
│   ├── app/
│   │   ├── api/{deps.py, router.py, endpoints/*}      # 40 OpenAPI paths
│   │   ├── core/{config,security,crypto,logging,exceptions}.py
│   │   ├── database/{session,integrity,backup,init_db}.py
│   │   ├── models/*                                   # 12 ORM models
│   │   ├── schemas/*                                  # Pydantic v2 contracts
│   │   ├── repositories/{audit,setting,route,job}_repo.py
│   │   ├── services/{telegram,ingestion,filter_engine,publishing}_service.py
│   │   ├── telegram/{gateway,listener,formatter}.py
│   │   ├── workers/runner.py
│   │   ├── utils/{time,sanitize,media}.py
│   │   └── main.py
│   ├── migrations/{env.py, versions/0001_initial_schema*.py}
│   ├── tests/ (6 modules, 15 tests)
│   ├── alembic.ini · pyproject.toml · requirements.txt
├── frontend/
│   ├── src/{components,contexts,hooks,layouts,pages,services,types,assets}
│   ├── tests/ (6 suites, 32 tests)
│   └── {vite.config.ts, tailwind.config.js, tsconfig.json, package.json}
├── docs/ (SRS, TDD, DATABASE, API, INSTALLATION, USER_GUIDE, DEPLOYMENT, TEST_REPORT + screenshots/)
├── scripts/ (backup_db.sh, restore_db.sh, setup_systemd.sh, push_to_github.sh, e2e_live_walkthrough.mjs)
├── deploy/{systemd/*.service, nginx/*.conf, docker/Dockerfile.*, docker-compose.yml}
├── .env.example · .gitignore · README.md · LICENSE
```

---

## 3. تدفّق البيانات (Data Flow)

### 3.1 استقبال منشور جديد
1. `TelethonClientManager` يفتح جلسة MTProto (StringSession مفكوكة من `telegram_accounts.encrypted_session`).
2. `listener.py` يستقبل `events.NewMessage` من القنوات النشطة (لا `MessageEdited`).
3. `IngestionService.handle_new_message()`:
   - يتحقق أن `message_id > baseline_message_id` (لا أرشيف).
   - إذا كان `grouped_id` ⇒ يضيفه إلى مُجمِّع الألبوم في الذاكرة وينتظر إغلاق النافذة.
   - يطبّع البيانات (نوع المحتوى، الوسائط، entities، `noforwards`).
   - **ينفّذ `INSERT` لـ`message_events` أولًا** (قيد فريد يمنع التكرار) ثم `message_media`، ثم `commit`.
   - يحسب الوجهات المطابقة من `publishing_routes` (نشطة + المصدر مفعّل + الوجهة مفعّلة).
   - لكل مسار: يطبّق `FilterEngine` (أنواع المحتوى، كلمات، طول نص، امتدادات، محتوى محمي) ويبني النص النهائي (`prefix` + نص + `suffix` + `signature`).
   - يُنشئ `publish_jobs` بحالة `QUEUED` (أو `SKIPPED` مع `skip_reason`) في نفس المعاملة.
4. `enqueued_at` يُسجَّل على الحدث بعد إنشاء المهام.

### 3.2 النشر
1. `WorkerOrchestrator.publisher_loop()` يستدعي `JobRepository.claim_next_job()` — استيلاء ذرّي (transaction) على أقدم `QUEUED` أو `RETRY_WAIT` المستحقة.
2. ينشئ `publish_attempts` بحالة `IN_FLIGHT` ويحوّل المهمة إلى `PROCESSING` مع `locked_by/locked_at/heartbeat_at`.
3. `PublishingEngine.publish_job()`:
   - يتحقق من صلاحية الوجهة (مفعّلة، وحدث الاتصال قائم).
   - ينشر: نص/وسائط/ألبوم عبر Telethon مع الحفاظ على `caption` وentities (بعد إزاحة offsets بصيغة UTF-16 لتناسب حدود تيليجرام).
   - يخزّن `target_message_id` (و`target_message_ids_json` للألبوم) و`published_at` ⇒ `PUBLISHED`.
4. عند الفشل:
   - أخطاء عابرة (FloodWait, network, RPC) ⇒ `RETRY_WAIT` مع `next_retry_at = now + min(base * 2^n, max)`.
   - استنفاد المحاولات أو أخطاء دائمة (صلاحيات، محتوى محذوف) ⇒ `FAILED` مع `last_error`.
   - تعطّل العملية أثناء `PROCESSING` ⇒ يكتشفها الـwatchdog (`heartbeat` قديم) ويحوّلها إلى `UNKNOWN` + `unknown_reason` (لا إعادة تلقائية).

### 3.3 المصالحة (Reconciliation)
`ReconciliationService.reconcile_unknown_job()`:
1. يقرأ آخر رسائل الوجهة (`iter_messages(limit≈30)`).
2. يقارن النص المطبّع و/أو الوسائط مع `transformed_text` والحدث الأصلي.
3. إن وُجد المنشور ⇒ `PUBLISHED` مع `target_message_id`، `reconciliation_checked_at`.
4. إن لم يوجد ⇒ (بطلب المستخدم) إعادة إلى `QUEUED` أو `FAILED` مع سبب موثّق.

---

## 4. القرارات التقنية (Architecture Decision Records)

### ADR-001 — SQLite + WAL بدل PostgreSQL
**القرار:** SQLite في وضع WAL، `foreign_keys=ON`, `busy_timeout=5000`, `synchronous=NORMAL`.
**السبب:** المتطلب يفرض SQLite؛ أحادي الخادم، بلا عمليات إدارة إضافية، أداء كافٍ للهدف (آلاف الرسائل/اليوم).
**العواقب:** يجب تشغيل **worker واحد** فقط؛ النسخ الاحتياطي عبر `Connection.backup` وليس نسخ الملف؛ النشر على خادم واحد.

### ADR-002 — طابور دائم في نفس قاعدة البيانات بدل Redis/Celery
**القرار:** جدول `publish_jobs` هو الطابور؛ Worker يستهلكه بـpolling (افتراضي 1.5s) مع قفل منطقي.
**السبب:** المتطلب: Persistent Queue + Worker دون تقنيات إضافية غير مطلوبة (لا Redis في التقنيات المعتمدة). Atomicity بين الحدث والمهام في معاملة واحدة.
**العواقب:** لا توزيع أفقي؛ التأخير الأدنى = فترة الـpolling (قابل للضبط).

### ADR-003 — Telethon + StringSession مشفّرة في قاعدة البيانات
**القرار:** لا ملفات `.session` على القرص؛ `StringSession` تُشفَّر بـFernet وتُخزَّن في العمود `encrypted_session`.
**السبب:** المتطلب: عدم كشف الجلسة + لا ملفات جلسة في المستودع. النسخ الاحتياطي للقاعدة يشمل الجلسة بأمان.
**العواقب:** تغيير `SESSION_ENCRYPTION_KEY` يبطل الجلسة (يتطلب إعادة ربط) — موثّق في DEPLOYMENT.

### ADR-004 — استرداد `PROCESSING` إلى `UNKNOWN` لا إلى `QUEUED`
**القرار:** المهام العالقة (تعطل/إعادة تشغيل) تصبح `UNKNOWN` وتتطلب مصالحة.
**السبب:** قد يكون تيليجرام استلم المنشور قبل التعطل؛ الإعادة العمياء تُنتج تكرارًا مرئيًا في الوجهة.
**العواقب:** تدخّل بشري/زر مصالحة؛ لا ادّعاء Exactly-Once.

### ADR-005 — إزاحة entities بصيغة UTF-16
**القرار:** `formatter.py` يعمل بوحدات UTF-16 (`len(utf-16-le)//2`) عند إضافة `prefix`/`suffix` وحساب offsets.
**السبب:** تيليجرام يقيس offsets بوحدات UTF-16؛ العدّ بأحرف Python (code points) يفسد التنسيق مع الإيموجي والعربية.
**العواقب:** مُختبَر في `test_05_unit_formatter_and_recovery.py`.

### ADR-006 — الواجهة تستخدم مسارات نسبية `/api/v1/...` فقط
**القرار:** `services/api.ts` يستدعي `/api/v1/...`؛ Vite/Nginx يمرّران الطلب للـBackend.
**السبب:** لا تعارض CORS، لا عناوين hard-coded، نفس الحزمة تعمل في التطوير والإنتاج.

### ADR-007 — المعاملات النقدية (Transactions) عند حدود الخدمة
**القرار:** كل عملية منطقية (حدث + مهام، إعادة المحاولة، المصالحة) تُغلَق في `commit()` واحد.
**السبب:** لا مهام معلّقة لحدث غير محفوظ ولا العكس.

### ADR-008 — التسجيل الأحمر (Redacting logging filter)
**القرار:** `core/logging.py` يمرّر كل سجل عبر تعبيرات تُخفي `api_hash`, `password`, `code`, `token`, `session`. الواجهة تعرض `has_api_hash` فقط.
**السبب:** المتطلب الأمني: لا رموز/كلمات/جلسات في السجلات.

---

## 5. واجهات برمجية (API surface)

40 مسارًا تحت `/api/v1`، موثّقة بـOpenAPI 3.1 (`/docs` للـSwagger UI، `/openapi.json` للمخطط). التفاصيل الكاملة في `docs/API.md`.

| مجموعة | المسارات |
|---|---|
| Auth | `POST /auth/login`, `GET /auth/me`, `POST /auth/change-password`, `PATCH /auth/language`, `GET/POST /auth/users` |
| Dashboard | `GET /dashboard/overview` |
| Telegram | `GET /telegram/status`, `POST /telegram/send-code`, `POST /telegram/verify-code`, `POST /telegram/verify-password`, `POST /telegram/reconnect`, `PATCH /telegram/auto-reconnect`, `POST /telegram/logout` |
| Sources | `GET/POST /sources`, `PATCH/DELETE /sources/{id}`, `POST /sources/{id}/verify`, `POST /sources/{id}/start`, `POST /sources/{id}/stop` |
| Targets | `GET/POST /targets`, `PATCH/DELETE /targets/{id}`, `POST /targets/{id}/verify`, `POST /targets/{id}/test-publish` |
| Routes | `GET/POST /routes`, `POST /routes/bulk`, `PATCH/DELETE /routes/{id}`, `POST /routes/{id}/toggle` |
| Messages | `GET /messages`, `GET /messages/{event_id}` |
| Queue | `GET /queue/jobs`, `GET /queue/jobs/{id}`, `POST /queue/jobs/{id}/retry`, `POST /queue/jobs/{id}/reconcile`, `POST /queue/jobs/{id}/cancel` |
| Logs | `GET /logs` |
| Settings | `GET/PUT /settings`, `GET /settings/integrity`, `GET/POST /settings/backups`, `GET /settings/backups/{file}/download`, `POST /settings/backups/restore` |
| Health | `GET /health` |

**الأخطاء** موحّدة: `{ "detail": "...", "code": "..." }` مع رموز HTTP صحيحة (400/401/403/404/409/422/500).

---

## 6. الواجهة الأمامية (Frontend design)

- **Routing:** React Router 6، `ProtectedRoute` (JWT + دور) + `AppLayout` (شريط جانبي سطح المكتب + Drawer للهاتف).
- **State:** Contexts فقط (`AuthContext`, `I18nContext`, `ToastContext`) + polling عبر `usePolling` (Dashboard 15s، Queue 10s، Telegram 12s، الباقي عند الطلب) — لا حاجة لمكتبة state خارجية.
- **i18n:** قاموس كامل AR/EN، `document.documentElement.dir` يُضبط تلقائيًا، تفضيل اللغة محفوظ للمستخدم في قاعدة البيانات + LS.
- **Types:** `src/types/index.ts` يطابق مخططات Pydantic حرفيًا.
- **الوصولية:** `role="dialog"`, `aria-modal`, `role="switch"`, `role="alert"`, تسميات `<label>` مرتبطة.

---

## 7. الأمان (Security design)

| الجانب | التنفيذ |
|---|---|
| كلمات المرور | Argon2id (`argon2-cffi`) |
| الجلسات | JWT HS256 + `token_version` (إبطال فوري عند تغيير كلمة المرور) |
| التشفير | Fernet (AES-128-CBC + HMAC-SHA256) لمفتاح API Hash والجلسة |
| RBAC | `require_admin` لحماية عمليات تيليجرام/الإعدادات/النسخ/المستخدمين |
| التحقق | Pydantic v2 صيغ/حدود/أنماط على كل مدخل |
| الأسرار | `.env` فقط (gitignored) + `.env.example` موثّق + Redaction في السجلات |
| الرؤوس | `X-Content-Type-Options`, `Referrer-Policy`, `Cache-Control: no-store` |
| النسخ | `chmod 0600` + SHA-256 + تحقق قبل الاستعادة |
| الشبكة | Nginx TLS + proxy إلى `127.0.0.1:8000` (الـAPI غير معرّض مباشرة) |

---

## 8. الأداء والتوسّع (Performance & Scaling)

- فهارس على: `publish_jobs(status, next_retry_at)`, `(target_channel_id, status)`, `message_events(source_channel_id, telegram_message_id) UNIQUE`, `audit_logs(created_at, level)`.
- الـWorker يعالج مهمة واحدة كل دورة افتراضيًا (آمن لـSQLite)؛ يمكن زيادة التوازي داخل نفس العملية عبر asyncio مع الحفاظ على كتابة متسلسلة.
- التوسّع الرأسي: خادم أقوى + WAL. التوسّع الأفقي (متعدد الخوادم) **غير مدعوم** بتصميم SQLite الحالي — بديله الموثّق: الترقية إلى PostgreSQL + طابور Redis مع الحفاظ على نفس الواجهات.

---

## 9. حدود معروفة (Known Limitations)

1. **لا Exactly-Once مطلق** (تيليجرام). التخفيف: `UNKNOWN` + مصالحة.
2. **الأرشفة**: لا يمكن استيراد منشورات قديمة (بقرار المتطلب).
3. **الحماية**: المحتوى المحمي يُرفض (`SKIPPED`)، لا يوجد تجاوز.
4. **بيانات الاعتماد** لا تُنشأ آليًا (تتطلب my.telegram.org + OTP بشري).
5. **القيود الزمنية للـCatch-up**: تعتمد على حدود `iter_messages` في تيليجرام وأقصى `TELEGRAM_CATCHUP_LIMIT`.
6. **ألبوم فشل جزئي**: العناصر الناجحة تُلتزم، والفاشلة تُعلَّم وتُوثَّق، ولا تُعاد المجموعة كاملة تلقائيًا.
7. **SQLite**: worker واحد، خادم واحد، النسخ الاحتياطي إلزامي (وثّق في DEPLOYMENT).
