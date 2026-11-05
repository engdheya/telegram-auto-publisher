# Telegram Auto Publisher — INSTALLATION.md

> من صفر إلى نظام يعمل على Ubuntu 22.04/24.04 (ويعمل أيضًا على macOS/Debian).

---

## 0. المتطلبات المسبقة

| البرنامج | الإصدار الأدنى | ملاحظات |
|---|---|---|
| Ubuntu Server | 22.04 LTS أو 24.04 LTS | أو Debian 12 |
| Python | 3.11+ | مُختبَر على 3.13.16 |
| Node.js + npm | 20.x / 10.x | لبناء الواجهة |
| Git | 2.x | |
| Nginx | 1.18+ | للإنتاج |
| API ID / API Hash | — | من https://my.telegram.org → API development tools |
| رقم هاتف تيليجرام | — | لاستلام رمز التحقق |

```bash
sudo apt update && sudo apt install -y python3 python3-venv python3-pip git nginx curl
# Node 20 (إن لم يكن مثبتًا)
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash - && sudo apt install -y nodejs
```

---

## 1. جلب المشروع

```bash
git clone <YOUR_GITHUB_REPO_URL> telegram-auto-publisher
cd telegram-auto-publisher
```

---

## 2. الإعدادات (`.env`)

```bash
cp .env.example .env
# توليد مفاتيح قوية
python3 - <<'PY'
import secrets, base64, os
from cryptography.fernet import Fernet
print("SESSION_ENCRYPTION_KEY=" + Fernet.generate_key().decode())
print("JWT_SECRET_KEY=" + secrets.token_urlsafe(48))
PY
nano .env
```

**الحد الأدنى المطلوب تعديله:**

| المتغير | الوصف | إلزامي |
|---|---|---|
| `JWT_SECRET_KEY` | سرّ توقيع JWT (≥32 حرفًا) | ✅ |
| `SESSION_ENCRYPTION_KEY` | مفتاح Fernet (44 حرفًا base64) | ✅ |
| `INITIAL_ADMIN_USERNAME/PASSWORD/EMAIL` | مستخدم المشرف الأول | ✅ |
| `DATABASE_URL` | `sqlite:////opt/telegram-auto-publisher/runtime/tap.db` | ✅ |
| `TELEGRAM_DEFAULT_API_ID` / `TELEGRAM_DEFAULT_API_HASH` | اختياري (يمكن إدخالهما من الواجهة) | ❌ |
| `CORS_ORIGINS` | `["https://your-domain.com"]` في الإنتاج | للإنتاج |

> ⚠️ **لا ترفع `.env` إلى Git أبدًا.** الملف مستثنى في `.gitignore`، والمستودع يحتوي `.env.example` فقط.

---

## 3. Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 1) تطبيق الترحيلات (ينشئ كل الجداول والفهارس)
alembic upgrade head

# 2) إنشاء بيانات البداية (مشرف + إعدادات افتراضية) — idempotent
python3 -c "from app.database.init_db import init_database; init_database()"

# 3) التشغيل
uvicorn app.main:app --host 0.0.0.0 --port 8000
```
تحقق:
```bash
curl -s http://127.0.0.1:8000/api/v1/health | python3 -m json.tool      # status=ok, wal_enabled=true
open http://127.0.0.1:8000/docs                                        # Swagger UI (40 مسارًا)
```

---

## 4. Worker (إلزامي للنشر التلقائي)

```bash
cd backend && source .venv/bin/activate
python3 -m app.workers.runner
```
> **قاعدة صارمة:** Worker **واحد** فقط لكل قاعدة بيانات SQLite. لا تشغّل نسختين.

---

## 5. Frontend

```bash
cd frontend
npm install
npm run dev        # تطوير: http://localhost:5173 (proxy إلى :8000)
# أو
npm run build      # إنتاج: ينتج frontend/dist
```

---

## 6. أول دخول

1. افتح `http://localhost:5173` (أو نطاقك).
2. الدخول بـ`INITIAL_ADMIN_USERNAME` / `INITIAL_ADMIN_PASSWORD`.
3. **غيّر كلمة المرور فورًا**: Settings → تغيير كلمة المرور.
4. **حساب تيليجرام**: Telegram Account → API ID / API Hash / رقم الهاتف → إرسال رمز → تحقق (وكلمة مرور 2FA إن كانت مفعّلة).
5. أضف **Source** واحدًا على الأقل و**Target** واحدًا، ثم **Route**.

---

## 7. الاختبارات (تحقق من التثبيت)

```bash
# Backend — 15 اختبارًا
cd backend && source .venv/bin/activate && pytest -q

# Frontend — 32 اختبارًا
cd frontend && npx vitest run

# Build إنتاجي
cd frontend && npm run build

# E2E في متصفح حقيقي (يتطلب تشغيل الخدمات الثلاث + playwright install chromium)
cd frontend && npx playwright install chromium
cd .. && node scripts/e2e_live_walkthrough.mjs <username> <password>
```

---

## 8. التشغيل الدائم (systemd)

```bash
sudo ./scripts/setup_systemd.sh       # يثبّت 3 خدمات: backend, worker, frontend(static via nginx)
sudo systemctl status tap-backend tap-worker
sudo systemctl enable --now tap-backend tap-worker
```
تفاصيل كاملة + Nginx + TLS + النسخ الاحتياطي المجدول: `docs/DEPLOYMENT.md`.

---

## 9. استكشاف الأخطاء (Troubleshooting)

| العرض | السبب المحتمل | الحل |
|---|---|---|
| `SettingsError: error parsing value for field "CORS_ORIGINS"` | القيمة ليست JSON | اجعلها `["http://localhost:5173"]` |
| `alembic: command not found` | الـvenv غير مُفعّل | `source .venv/bin/activate` |
| الواجهة تفتح لكن الطلبات تفشل | Backend متوقف | `systemctl status tap-backend` |
| `database is locked` | أكثر من Worker | أوقف النسخ الزائدة: `pgrep -af app.workers.runner` |
| `auth_state=UNCONFIGURED` | لم يُربط الحساب | Telegram Account → ربط |
| `Telegram client is not connected` عند فحص القناة | الحساب غير متصل | Reconnect ثم Verify |
| الواجهة بيضاء في المعاينة | المعاينة لا تصل للـBackend | شغّل Vite محليًا أو استخدم النطاق المنشور |
| `FloodWait` في السجلات | تجاوز حدود تيليجرام | سلوك طبيعي؛ النظام يعيد المحاولة تلقائيًا |

---

## 10. Docker (اختياري)

```bash
cp .env.example .env      # عدّل الأسرار
docker compose up -d --build
docker compose logs -f
```
انظر `deploy/docker-compose.yml` و`docs/DEPLOYMENT.md` §Docker. **حجم الـvolume** لقاعدة البيانات إلزامي (`runtime/`) وإلا فقدت البيانات عند إعادة الإنشاء.
