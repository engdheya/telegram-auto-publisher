# Telegram Auto Publisher — SRS (Software Requirements Specification)

> Version 1.0.0 · Status: **Delivered / Production-Ready** · Language: Arabic (EN summary at the end)

---

## 1. الهدف (Purpose)

نظام خادم (self-hosted) لمراقبة **قنوات تيليجرام مصدر** ونشر المنشورات **الجديدة فقط** تلقائيًا في **قنوات وجهة** متعددة، وفق مسارات (Routes) مستقلة يُديرها المستخدم من لوحة تحكم ويب ثنائية اللغة (عربي/إنجليزي).

المخرَج منتج برمجي متكامل End-to-End — وليس نموذجًا أوليًا — يشمل: Backend + Database + Telegram Listener + Publishing Worker + Web Dashboard + Tests + Deployment.

---

## 2. أصحاب المصلحة (Stakeholders)

| الدور | الوصف | الصلاحيات |
|---|---|---|
| **Admin** | مالك الحساب/النظام | كل شيء: ربط حساب تيليجرام، إدارة المصادر/الوجهات/المسارات، إعدادات النظام، النسخ الاحتياطي/الاستعادة، إدارة المستخدمين |
| **Operator** | مشغّل يومي | عرض كل الصفحات، إدارة المصادر/الوجهات/المسارات، متابعة الطابور والسجلات، تغيير كلمة المروره الشخصية، **لا** يمكنه ربط حساب تيليجرام أو تغيير إعدادات النظام أو النسخ الاحتياطي أو إنشاء مستخدمين |

RBAC مفروض على مستوى الـAPI عبر `require_admin` / `get_current_user` — وليس في الواجهة فقط.

---

## 3. المتطلبات الوظيفية (Functional Requirements)

### FR-1 إدارة حساب Telegram
- FR-1.1 ربط الحساب بـ `API ID` + `API Hash` + رقم الهاتف.
- FR-1.2 إرسال رمز OTP والتحقق منه عبر Telegram (`send_code_request` / `sign_in`).
- FR-1.3 دعم كلمة مرور التحقق بخطوتين (2FA).
- FR-1.4 حفظ الجلسة **مشفّرة** (Fernet/AES-128-CBC+HMAC) في `telegram_accounts.encrypted_session`؛ لا تُكتب في ملفات نصية ولا تُعاد في أي استجابة API.
- FR-1.5 عرض حالة الاتصال (`auth_state`: `UNCONFIGURED | DISCONNECTED | AWAITING_CODE | AWAITING_PASSWORD | CONNECTED | AUTH_ERROR`) + نبضة الاتصال (heartbeat).
- FR-1.6 إعادة اتصال تلقائية عند الانقطاع (watchdog + `auto_reconnect`).
- FR-1.7 إعادة اتصال يدوية من الواجهة (وتُشغّل catch-up للرسائل الفائتة).
- FR-1.8 تسجيل خروج / إلغاء ربط يمحو الجلسة المشفرة ويحذف `session` نهائيًا.

### FR-2 قنوات المصدر (Sources)
- FR-2.1 إضافة/تعديل/حذف/تفعيل/تعطيل عدد غير محدود من القنوات (`@username` أو رابط أو Peer ID رقمي).
- FR-2.2 التحقق من إمكانية الوصول عبر Telethon (`get_entity`) وتسجيل نتيجة التحقق أو الخطأ.
- FR-2.3 بدء/إيقاف المراقبة لكل قناة على حدة (`ACTIVE | PAUSED | UNVERIFIED | ERROR`).
- FR-2.4 تسجيل `baseline_message_id` عند أول مراقبة = **أعلى معرّف رسالة موجود**، و`last_processed_message_id` بعد كل معالجة.
- FR-2.5 عرض أخطاء الاتصال/الصلاحيات وحالة حماية المحتوى (`noforwards_protected`).

### FR-3 قنوات الوجهة (Targets)
- FR-3.1 إضافة/تعديل/حذف/تفعيل/تعطيل.
- FR-3.2 التحقق من صلاحيات النشر (`can_post_messages`, `can_post_media`) وحفظ `permission_status`.
- FR-3.3 اختبار نشر فعلي (رسالة حقيقية تُرسل للوجهة) وإظهار سبب الفشل كما يعيده تيليجرام.

### FR-4 مسارات النشر (Routes)
- FR-4.1 مسار مستقل لكل زوج (`Source → Target`) مع 1→1 و1→N و1→1 متعدد و N→N.
- FR-4.2 باني ربط متعدد N×M ينشئ كل الأزواج في طلب واحد (تخطي المكرر دون فشل).
- FR-4.3 تبديل حالة المسار بشكل مستقل تمامًا (تعطيل مسار لا يؤثر على غيره).
- FR-4.4 حذف مسار لا يحذف المصادر/الوجهات ولا المسارات الأخرى.
- FR-4.5 `route_filters`: أنواع المحتوى المسموحة، كلمات للتضمين، كلمات للاستبعاد، حد أدنى/أقصى لطول النص، بادئة، لاحقة، توقيع خاص بالوجهة، امتدادات الملفات المسموحة، حذف الروابط.

### FR-5 استقبال المنشورات (Ingestion)
- FR-5.1 مراقبة **المنشورات الجديدة فقط** عبر Telethon `NewMessage` (لا استيراد أرشيف).
- FR-5.2 بداية المراقبة من `baseline_message_id` الموثّق لكل مصدر.
- FR-5.3 عند عودة الاتصال: محاولة التقاط الرسائل الفائتة (`iter_messages` بحد أعلى قابل للضبط `TELEGRAM_CATCHUP_LIMIT`) ضمن حدود تيليجرام.
- FR-5.4 تجاهل التعديلات (`MessageEdited` غير مسجّل) والحذف تمامًا.
- FR-5.5 حفظ كل حدث في `message_events` **قبل** إنشاء مهام النشر (`publish_jobs`).
- FR-5.6 منع التكرار بقيد فريد `(source_channel_id, telegram_message_id)` + `grouped_id`.
- FR-5.7 معالجة متزامنة آمنة (WAL + معاملات + طابور دائم).

### FR-6 المحتوى المدعوم
- FR-6.1 نص، صورة واحدة، فيديو، ملف، صوت، رسالة صوتية، وسائط متعددة، ألبومات، تعليقات توضيحية (captions)، وentities منسّقة.
- FR-6.2 الألبوم: تجميع بـ`grouped_id` داخل نافذة (`ALBUM_AGGREGATION_WINDOW_MS`) مع الحفاظ على الترتيب والـcaption، ومنع تكرار الألبوم كاملًا عند فشل عنصر واحد (`album_status`, `message_media.status`).
- FR-6.3 المحتوى المحمي (`noforwards`) وقيود الصلاحيات: تُسجَّل المهمة `SKIPPED` مع سبب واضح، **دون أي محاولة تجاوز**.

### FR-7 محرك النشر (Publishing Engine)
- FR-7.1 مهمة مستقلة لكل (حدث × مسار × وجهة).
- FR-7.2 الحالات: `QUEUED`, `PROCESSING`, `PUBLISHED`, `RETRY_WAIT`, `SKIPPED`, `FAILED`, `UNKNOWN`.
- FR-7.3 سياسة إعادة محاولة أسّية (exponential backoff) قابلة للضبط (`retry.max_attempts`, `retry.base_seconds`, `retry.max_seconds`).
- FR-7.4 فشل وجهة لا يعيد نشر الوجهات الناجحة (كل مهمة مستقلة، ولا يوجد "نشر جماعي" في المعاملة الواحدة).
- FR-7.5 `UNKNOWN` عند التعطل أثناء النشر (استرداد الأقفال القديمة) + خدمة مصالحة تتحقق من الرسائل الأخيرة في الوجهة قبل أي إعادة.
- FR-7.6 لا يُدّعى ضمان Exactly-Once مطلق (تيليجرام لا يوفّره) — يُوثَّق القيد ويُقلَّل احتمال التكرار بالمصالحة.
- FR-7.7 إعادة المحاولة اليدوية الآمنة، والإلغاء، من الواجهة.

### FR-8 لوحة التحكم
عشر صفحات كاملة الوظائف (Login, Dashboard, Telegram Account, Sources, Targets, Routes, Messages, Queue, Logs, Settings) بالعربية RTL والإنجليزية LTR، متجاوبة مع الهاتف والكمبيوتر، وكل زر فيها موصول فعليًا بالـBackend.

### FR-9 السجلات (Audit & Logs)
- FR-9.1 سجل تدقيق لكل عملية (فاعل، فئة، نوع العملية، كيان، تفاصيل JSON، IP).
- FR-9.2 تصفية حسب المستوى/الفئة + بحث نصي + عرض JSON خام.
- FR-9.3 إخفاء (Redaction) رموز التحقق وكلمات المرور ومفاتيح API والجلسات قبل الكتابة في السجلات.

### FR-10 الإعدادات والنسخ الاحتياطي
- FR-10.1 إعدادات نظام في قاعدة البيانات (`system_settings`) قابلة للتعديل من الواجهة (اللغة، الإعادة، التخزين، الأمان).
- FR-10.2 فحص سلامة SQLite (`PRAGMA integrity_check` + `foreign_key_check` + `journal_mode` + وجود الـ12 جدولًا للتطبيق، و13 إجمالًا مع `alembic_version`).
- FR-10.3 نسخة احتياطية متسقة أثناء التشغيل (`sqlite3.Connection.backup`) + SHA-256 + صلاحيات `0600` + تنزيل من الواجهة.
- FR-10.4 استعادة مع نسخة أمان تلقائية قبلها وتحقق من الـchecksum.

### FR-11 إدارة المستخدمين
- FR-11.1 إنشاء مستخدمين بأدوار (admin/operator) وكلمات مرور Argon2id.
- FR-11.2 تغيير كلمة المرور يُبطل كل الجلسات القديمة (token_version).

---

## 4. المتطلبات غير الوظيفية (Non-Functional)

| # | المتطلب |
|---|---|
| NFR-1 | **الأمان**: Argon2id، JWT (HS256, انتهاء صلاحية)، Fernet للتشفير، حماية endpoints، RBAC، تحقق مدخلات Pydantic، Security headers، لا أسرار في Git/SIEM/الواجهة |
| NFR-2 | **الاعتمادية**: طابور دائم في SQLite، استرداد المهام العالقة عند إعادة التشغيل، معاملات ACID، WAL + `busy_timeout` |
| NFR-3 | **قابلية التشغيل على Ubuntu Server 22.04/24.04** عبر systemd (backend/worker/frontend) خلف Nginx |
| NFR-4 | **الأداء المستهدف**: ~50 مصدرًا، ~200 وجهة، ~5,000 منشور/يوم على جهاز واحد (SQLite WAL) |
| NFR-5 | **قابلية المراقبة**: Logs دوّارة في `runtime/logs/`، `/api/v1/health`، نبضة worker على الـDashboard |
| NFR-6 | **قابلية الصيانة**: فصل مسؤوليات صارم (api / services / repositories / models / telegram / workers)، Alembic migrations |
| NFR-7 | **i18n**: عربي RTL كامل + إنجليزي LTR، تبديل فوري وحفظ التفضيل لكل مستخدم |
| NFR-8 | **Оперативность**: نسخ/استعادة قاعدة البيانات أثناء التشغيل دون إيقاف الخدمة |

---

## 5. القيود المفروضة (Constraints)

1. **لا استيراد أرشيف**: أول تشغيل يسجل `baseline_message_id` فقط.
2. **لا نشر للتعديلات ولا للحذف**.
3. **لا تجاوز لحماية المحتوى**: `noforwards` ⇒ `SKIPPED` مع السبب.
4. **لا Exactly-Once مطلق**: تيليجرام لا يوفّره؛ استراتيجية `UNKNOWN` + مصالحة.
5. **SQLite**:instance واحد + **worker واحد** لكل قاعدة بيانات. لا تشغّل عدة Workers مستقلة على نفس الملف.
6. **حدود تيليجرام**: FloodWait، حدود رفع الوسائط، وحجم الملفات (2GB لكلا النوعين، 4GB للـPremium) تُعالَج كأخطاء قابلة لإعادة المحاولة أو كـ`FAILED` مع سبب.
7. **بيانات الاعتماد**: الربط يتطلب الحصول على API ID/Hash من `my.telegram.org` — لا يمكن للنظام إنشاءها.

---

## 6. معايير القبول (Acceptance Criteria) — الحالة

| # | المعيار | الحالة | الدليل |
|---|---|---|---|
| 1 | تثبيت من الصفر وفق التوثيق | ✅ | `docs/INSTALLATION.md` |
| 2 | تشغيل Backend + Frontend + Worker | ✅ | 3 خدمات systemd + تشغيل حقيقي مُختبَر |
| 3 | تسجيل الدخول للوحة التحكم | ✅ | `test_02_auth_and_security.py` + E2E حقيقي |
| 4 | ربط حساب Telegram (OTP + 2FA) | ✅ (كود) | `test_03_telegram_connection.py` — يتطلب API ID/Hash من المستخدم |
| 5 | إضافة عدة مصادر/وجهات | ✅ | `test_06`, E2E |
| 6 | إنشاء عدة مسارات (1→N, N→M) | ✅ | `test_04_e2e_all_12_scenarios.py` |
| 7 | استقبال المنشورات الجديدة تلقائيًا | ✅ | Scenario 1–6 |
| 8 | نشر النصوص والوسائط | ✅ | Scenario 9–10 |
| 9 | معالجة الألبومات | ✅ | Scenario 9 |
| 10 | لا استيراد أرشيف | ✅ | Scenario 4 |
| 11 | لا نشر للتعديلات | ✅ | Scenario 4 |
| 12 | طابور دائم | ✅ | `publish_jobs` + WAL |
| 13 | منع التكرار + معالجة UNKNOWN | ✅ | Scenario 11 + `ReconciliationService` |
| 14 | فشل وجهة لا يؤثر على الناجحة | ✅ | Scenario 8 |
| 15 | حالة المهام والأخطاء ظاهرة في الواجهة | ✅ | Queue/Messages/Logs |
| 16 | الأزرار تعمل فعليًا | ✅ | 20/20 فحص E2E في متصفح حقيقي + فيديو عرض `docs/media/` |
| 17 | الاختبارات تنجح | ✅ | 15 Python + 32 Frontend + 20 E2E |
| 18 | وثائق التثبيت/التشغيل/الاستخدام/النشر | ✅ | `docs/*.md` |
| 19 | لا أسرار في المستودع | ✅ | `.gitignore` + فحص `git ls-files` |
| 20 | اختبار عملي على حساب وقنوات حقيقية | ⚠️ **مُجهَّز لكن غير مُنفَّذ**: السكربت الجاهز `scripts/live_telegram_e2e.py` ينفّذ كل الفحوص على تيليجرام الحقيقي، لكنه يحتاج `API_ID/API_HASH` + هاتف + قنوات مصرّح بها منك | `docs/LIVE_TELEGRAM_EVIDENCE.md` §الحالة |

---

## 7. English summary

Functional scope: Telegram MTProto account linking (OTP + 2FA, encrypted session, auto-reconnect), multi-source monitoring with documented `baseline_message_id` (no archive import, no edit/delete relaying), multi-target publishing through independent routes (1→1, 1→N, N→1, N→N), per-route filter rules, albums via `grouped_id`, persistent SQLite queue with the 7 required job states, exponential retry, `UNKNOWN` reconciliation, protected-content refusal (`SKIPPED`), bilingual dashboard, audit logs, settings, integrity checks and online backup/restore.

Non-functional: Argon2id + JWT + Fernet, RBAC, WAL SQLite with FK enforcement, single-worker rule, systemd + Nginx deployment, pytest/Vitest/Playwright test pyramid.

Explicitly **not** claimed: absolute exactly-once delivery (Telegram offers none), archive back-fill, edit/deletion propagation, or bypassing `noforwards` protection.
