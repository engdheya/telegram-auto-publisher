# Telegram Auto Publisher

> **نظام إنتاجي متكامل** لمراقبة قنوات تيليجرام ونشر منشوراتها الجديدة تلقائيًا في قنوات وجهة متعددة، وفق مسارات (Routes) مستقلة وقواعد تصفية، مع لوحة تحكم ويب عربية/إنجليزية.
>
> **Production-ready** Telegram channel relay engine: monitor multiple source channels, publish new posts to multiple targets through independent, filterable routes — with a bilingual (AR/EN) React dashboard, a persistent SQLite queue, a background worker, and full test coverage.

![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?style=flat-square)
![FastAPI](https://img.shields.io/badge/FastAPI-OpenAPI_3.1-009688?style=flat-square)
![Telethon](https://img.shields.io/badge/Telethon-MTProto-2CA5E0?style=flat-square)
![React](https://img.shields.io/badge/React_18-TypeScript-61DAFB?style=flat-square)
![Tailwind](https://img.shields.io/badge/TailwindCSS-3-38BDF8?style=flat-square)
![SQLite](https://img.shields.io/badge/SQLite-WAL-003B57?style=flat-square)
![Tests](https://img.shields.io/badge/tests-67_passing_(15_pytest_·_32_vitest_·_20_e2e)-success?style=flat-square)
![License](https://img.shields.io/badge/license-MIT-green?style=flat-square)

---

## المحتويات | Table of contents

- [لماذا هذا المشروع](#لماذا-هذا-المشروع)
- [المزايا](#المزايا-features)
- [المعمارية](#المعمارية-architecture)
- [التقنيات](#التقنيات-tech-stack)
- [التشغيل السريع](#التشغيل-السريع-quick-start)
- [الواجهة](#الواجهة-dashboard)
- [الاختبارات](#الاختبارات-tests)
- [الوثائق](#الوثائق-documentation)
- [القيود المعروفة](#القيود-المعروفة-known-limitations)
- [GitHub workflow](#github-workflow)
- [License](#license)

---

## لماذا هذا المشروع

تشغيل "نقل تلقائي" بين قنوات تيليجرام عادةً ينتهي بسكربت هش: يكرر المنشورات، يعيد نشرها بعد إعادة التشغيل، ينشر أرشيفًا قديمًا، أو يتوقف بصمت عند أول انقطاع شبكة. هذا المشروع يعالج تلك المشاكل بهندسة صريحة:

| المشكلة الشائعة | الحل هنا |
|---|---|
| إعادة نشر أرشيف القناة عند أول تشغيل | `baseline_message_id` يُسجَّل قبل بدء المراقبة — **لا استيراد للأرشيف** |
| تكرار المنشور نفسه بسبب إعادة الاتصال | قيد `UNIQUE(source_channel_id, telegram_message_id)` + سجل `publish_attempts` |
| فشل وجهة يعيد نشر الوجهات الناجحة | مهمة مستقلة لكل (حدث × وجهة) + `UNIQUE(message_event_id, target_channel_id)` |
| تعطّل أثناء النشر ⇒ نشر مزدوج صامت | الحالة `UNKNOWN` + **مصالحة** تتحقق من الوجهة قبل أي إعادة |
| أسرار الجلسة على القرص | `StringSession` **مشفّرة بـFernet** داخل قاعدة البيانات، ولا تُعاد في أي API |
| تعديل/حذف المنشور يُنشر خطأً | لا معالج `MessageEdited` — التعديلات والحذف متجاهلة بالتصميم |
| تجاوز حماية المحتوى | `noforwards` ⇒ `SKIPPED` بسبب صريح، **دون أي محاولة تجاوز** |

---

## المزايا (Features)

### حساب Telegram
- ربط بـ `API ID` / `API Hash` / رقم الهاتف، تسجيل دخول OTP + **2FA**.
- جلسة مشفّرة دائمة، حالة اتصال حيّة، إعادة اتصال تلقائية ويدوية، تسجيل خروج/إعادة ربط.
- **لا يُعرض** الـAPI Hash ولا بيانات الجلسة في الواجهة أو السجلات (Redaction).

### المصادر (Sources)
- إضافة/تعديل/حذف/تفعيل/تعطيل عدة قنوات، فحص الوصول عبر Telethon، بدء/إيقاف المراقبة.
- تتبّع `baseline_message_id` و`last_processed_message_id`، وعرض أخطاء الاتصال/الصلاحيات، وكشف `noforwards`.

### الوجهات (Targets)
- إضافة/تعديل/حذف/تفعيل/تعطيل، فحص صلاحيات النشر (`can_post_messages`/`can_post_media`)، **اختبار نشر حقيقي** يعرض رد تيليجرام الحرفي.

### المسارات (Routes)
- **1→1، 1→N، N→1، N→N** — مسار مستقل لكل زوج، تبديل/حذف دون التأثير على غيره.
- باني **ربط متعدد N×M** ذرّي (مصدران × 3 وجهات = 6 مسارات في طلب واحد).
- `route_filters`: أنواع المحتوى، كلمات تضمين/استبعاد، حد أدنى/أقصى للنص، امتدادات الملفات، نص قبل/بعد، توقيع الوجهة، حذف الروابط.

### الاستقبال والمحتوى
- **المنشورات الجديدة فقط**؛ التقاط الرسائل الفائتة بعد الانقطاع ضمن حدود تيليجرام؛ تجاهل التعديلات والحذف.
- نص، صورة، فيديو، ملف، صوت، رسالة صوتية، وسائط متعددة، **ألبومات** (`grouped_id` مع الحفاظ على الترتيب/التعليق)، تنسيق entities مع إزاحة UTF‑16 صحيحة.

### محرك النشر
- طابور دائم في SQLite، حالات: `QUEUED · PROCESSING · PUBLISHED · RETRY_WAIT · SKIPPED · FAILED · UNKNOWN`.
- إعادة محاولة أسّية قابلة للضبط، استرداد المهام العالقة عند إعادة التشغيل، مصالحة UNKNOWN، إلغاء يدوي.

### لوحة التحكم
- عشر صفحات كاملة الوظائف، **كل زر موصول بالـBackend وقاعدة البيانات فعليًا** (تم التحقق بفحص E2E في متصفح حقيقي: 20/20).
- ثنائية اللغة AR (RTL) / EN (LTR)، متجاوبة مع الهاتف، إشعارات، مودالات تأكيد، تحديث تلقائي للمؤشرات والطابور.

### الأمان والتشغيل
- Argon2id، JWT + `token_version`، Fernet، RBAC (admin/operator)، تحقق مدخلات Pydantic، رؤوس أمان.
- فحص سلامة SQLite من الواجهة، نسخ احتياطي **online متسق** + SHA‑256، استعادة مع نسخة أمان.
- systemd (backend + worker + نسخ مجدول) + Nginx + Docker Compose.

---

## المعمارية (Architecture)

```
Browser ──HTTPS──► Nginx ──/api──► FastAPI (40 OpenAPI paths) ──► SQLAlchemy ──► SQLite (WAL)
                        └──SPA──► React 18 dist                         ▲
                                                                        │
             Telethon MTProto ◄── worker (single instance) ◄────────────┘
             (listener → message_events → publish_jobs → publish_attempts)
```

| الطبقة | المجلد |
|---|---|
| API + OpenAPI | `backend/app/api/` (`endpoints/`, `deps.py`) |
| الخدمات (استقبال/تصفية/نشر/مصالحة) | `backend/app/services/` |
| Telethon (gateway/listener/formatter) | `backend/app/telegram/` |
| Worker | `backend/app/workers/runner.py` |
| النماذج والمخططات | `backend/app/models/`, `backend/app/schemas/` |
| قاعدة البيانات والنسخ | `backend/app/database/` (`session`, `integrity`, `backup`) |
| الواجهة | `frontend/src/` (`pages`, `components`, `contexts`, `services`, `types`) |
| الوثائق والعمليات | `docs/`, `scripts/`, `deploy/` |

**12 جدولًا:** `users`, `telegram_accounts`, `source_channels`, `target_channels`, `publishing_routes`, `route_filters`, `message_events`, `message_media`, `publish_jobs`, `publish_attempts`, `audit_logs`, `system_settings` — مع FKs، قيود UNIQUE، فهارس، وترحيلات Alembic.

---

## التقنيات (Tech stack)

Python 3.11+ · Telethon · FastAPI (OpenAPI/Swagger) · SQLAlchemy 2 · Alembic · SQLite (WAL) · Pydantic v2 · Argon2id + Fernet · **React 18 + TypeScript + Tailwind CSS** · Vite · Vitest + Testing Library · Playwright · pytest · systemd · Nginx · Docker Compose (اختياري).

---

## التشغيل السريع (Quick start)

```bash
# 1) الكود
git clone <YOUR_REPO_URL> telegram-auto-publisher && cd telegram-auto-publisher

# 2) الإعدادات
cp .env.example .env
python3 - <<'PY'
import secrets
from cryptography.fernet import Fernet
print("SESSION_ENCRYPTION_KEY=" + Fernet.generate_key().decode())
print("JWT_SECRET_KEY=" + secrets.token_urlsafe(48))
PY
nano .env      # ضع المفاتيح + كلمة مرور المشرف + مسار DATABASE_URL

# 3) Backend
cd backend && python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
python3 -c "from app.database.init_db import init_database; init_database()"
uvicorn app.main:app --host 0.0.0.0 --port 8000        # terminal 1

# 4) Worker (terminal 2)
cd backend && source .venv/bin/activate && python3 -m app.workers.runner

# 5) Dashboard (terminal 3)
cd frontend && npm install && npm run dev               # http://localhost:5173
```

ثم: سجّل الدخول → اربط حساب تيليجرام → أضف مصدرًا ووجهة → أنشئ مسارًا → راقب النشر.

**الإنتاج:** `sudo ./scripts/setup_systemd.sh` + Nginx (`deploy/nginx/`) — التفاصيل في [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md).

---

## الواجهة (Dashboard)

| الصفحة | الوظيفة |
|---|---|
| Login | JWT، حماية الجلسة، عرض سبب الرفض الحقيقي |
| Dashboard | حالة تيليجرام/Worker/قاعدة البيانات + 8 مؤشرات + آخر الأنشطة |
| Telegram Account | حالة، ربط، OTP/2FA، reconnect، logout (بلا أسرار) |
| Sources | قائمة/إضافة/تعديل/حذف/تفعيل/فحص الوصول/بدء وإيقاف المراقبة |
| Targets | قائمة/إضافة/تعديل/حذف + فحص الصلاحيات + اختبار نشر فعلي |
| Routes | مسار مفرد + باني N×M + محرر `route_filters` كامل + تبديل مستقل |
| Messages | سجل الأحداث + الوسائط + مهام كل وجهة + سبب الفشل + إعادة محاولة |
| Queue | تبويبات الحالات + محاولات + Retry + مصالحة UNKNOWN + إلغاء |
| Logs | مستوى/فئة/بحث + درج JSON |
| Settings | إعدادات النظام، كلمة المرور، المستخدمون، سلامة القاعدة، نسخ/استعادة |

لقطات حقيقية من النظام العامل: `docs/screenshots/` (16 صورة: عربي/إنجليزي/هاتف).

---

## الاختبارات (Tests)

```bash
cd backend  && pytest -q          # 15 passed   (DB/WAL/قيود، أمان، Telethon، 12 سيناريو، استرداد، API)
cd frontend && npx vitest run     # 32 passed   (6 مجموعات: مصادقة، مؤشرات، مصادر/وجهات، مسارات، رسائل/طابور، إعدادات/i18n)
cd frontend && npm run build      # 0 TypeScript errors، build إنتاجي ناجح
node scripts/e2e_live_walkthrough.mjs <user> <pass>   # 20/20 فحصًا في Chromium حقيقي ضد النظام الحيّ
```

التقرير الكامل بالنتائج والسيناريوهات: [`docs/TEST_REPORT.md`](docs/TEST_REPORT.md).

---

## الوثائق (Documentation)

| الملف | المحتوى |
|---|---|
| [`docs/SRS.md`](docs/SRS.md) | متطلبات وظيفية/غير وظيفية، معايير القبول وحالتها |
| [`docs/TDD.md`](docs/TDD.md) | المعمارية، تدفق البيانات، 8 قرارات تقنية (ADR) |
| [`docs/DATABASE.md`](docs/DATABASE.md) | المخطط الكامل، القيود، الفهارس، الترحيلات، النسخ/الاستعادة |
| [`docs/API.md`](docs/API.md) | كل مسارات REST + أمثلة استجابة + cURL |
| [`docs/INSTALLATION.md`](docs/INSTALLATION.md) | التثبيت من الصفر + استكشاف الأخطاء |
| [`docs/USER_GUIDE.md`](docs/USER_GUIDE.md) | دليل استخدام كل صفحة وسيناريوهات يومية |
| [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) | systemd + Nginx + TLS + نسخ مجدول + Docker + قائمة Go‑Live |
| [`docs/TEST_REPORT.md`](docs/TEST_REPORT.md) | نتائج الاختبارات الحقيقية ومصفوفة التغطية |

---

## القيود المعروفة (Known limitations)

1. **لا ضمان Exactly‑Once مطلق** — تيليجرام لا يوفّره. التخفيف: حالة `UNKNOWN` + مصالحة تتحقق من الوجهة قبل الإعادة.
2. **لا استيراد أرشيف** ولا **نشر للتعديلات/الحذف** — قرار تصميمي مقصود.
3. **المحتوى المحمي (`noforwards`)** يُسجَّل `SKIPPED` ولا يُنشر؛ لا يوجد تجاوز.
4. **SQLite**: Worker **واحد** لكل قاعدة بيانات وخادم واحد. التوسّع الأفقي يتطلب PostgreSQL + طابور موزّع (موثّق في TDD).
5. **حدود تيليجرام**: `FloodWait` وحجم الوسائط تُعالَج كإعادة محاولة أو `FAILED` مع سبب.
6. **الربط الفعلي بحساب تيليجرام** يتطلب `API ID/Hash` من [my.telegram.org](https://my.telegram.org) + رمز OTP — لا يمكن للنظام توليدها. الاختبارات الآلية تستخدم `FakeTelegramGateway` الحتمي، بينما كود Telethon الحقيقي هو المستخدم في الإنتاج.

---

## GitHub workflow

```bash
./scripts/push_to_github.sh git@github.com:<user>/<repo>.git
```
السكربت يرفض الدفع إن كان أي ملف حساس (`.env`, `*.session`, `*.db`, `dist/`, `node_modules/`) متتبعًا، ثم يدفع الفرع الحالي ويضبط `origin`.
CI جاهز في `.github/workflows/ci.yml` (تثبيت + pytest + vitest + build). قوالب Issues/PRs في `.github/`.

> **لا تُرفع أبدًا**: `.env`، ملفات `.session`، قواعد بيانات حقيقية، نسخ احتياطية، أو مفاتيح.

---

## License

MIT — انظر [`LICENSE`](LICENSE).

---

<div dir="rtl">

**باختصار:** استنسخ المستودع، اضبط `.env` وبيانات تيليجرام، شغّل `alembic upgrade head` ثم الخدمات الثلاث، وابدأ بإدارة مصادرك ووجهاتك من لوحة التحكم مباشرة.

</div>
