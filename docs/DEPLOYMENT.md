# Telegram Auto Publisher — DEPLOYMENT.md

> نشر إنتاجي على **Ubuntu Server 22.04/24.04** مع systemd + Nginx + TLS، أو باستخدام **Docker Compose**.
> **قواعد إلزامية**: (1) Worker **واحد** لكل قاعدة بيانات. (2) تخزين SQLite دائم. (3) نسخ احتياطي يومي.

---

## 1. التخطيط المعماري للإنتاج

```
Internet ──► Nginx :443 (TLS, static SPA) ──► 127.0.0.1:8000 (uvicorn/FastAPI)
                                          └── /assets من /opt/tap/frontend/dist
                                                    │
                                            /opt/tap/runtime/tap.db  (SQLite WAL)
                                                    ▲
                              tap-worker.service ───┘  (WorkerOrchestrator, نسخة واحدة)
```

| الوحدة | نوع systemd | ملاحظات |
|---|---|---|
| `tap-backend.service` | خدمة ويب | uvicorn، 2–4 عمال **قراءة فقط للـAPI** (لا تنشر) |
| `tap-worker.service` | خدمة خلفية | **نموذج واحد فقط** (`Restart=always`) |
| `nginx` | خدمة نظام | TLS + SPA + proxy |

> لا تُشغّل `tap-backend` بأكثر من عملية واحدة عند استخدام SQLite للكتابة الكثيفة؛ العملية الواحدة للـAPI + عملية Worker تكفي لآلاف الرسائل يوميًا.

---

## 2. التحضير على الخادم

```bash
sudo useradd -r -m -d /opt/tap -s /bin/bash tap
sudo mkdir -p /opt/tap && sudo chown tap:tap /opt/tap
sudo -u tap git clone <YOUR_REPO_URL> /opt/tap/app
cd /opt/tap/app

# Python venv
sudo -u tap python3 -m venv /opt/tap/venv
sudo -u tap /opt/tap/venv/bin/pip install --upgrade pip
sudo -u tap /opt/tap/venv/bin/pip install -r backend/requirements.txt

# Frontend build
sudo -u tap bash -c 'cd frontend && npm ci && npm run build'

# Runtime dirs
sudo -u tap mkdir -p /opt/tap/runtime/{backups,logs,media_cache}
sudo chmod 750 /opt/tap/runtime
```

### `.env` للإنتاج

```bash
sudo -u tap cp .env.example /opt/tap/app/.env
sudo -u tap nano /opt/tap/app/.env
```

```dotenv
APP_ENV=production
JWT_SECRET_KEY=<48+ random chars>
SESSION_ENCRYPTION_KEY=<Fernet key>
INITIAL_ADMIN_USERNAME=admin
INITIAL_ADMIN_EMAIL=admin@your-domain.com
INITIAL_ADMIN_PASSWORD=<strong password — change after first login>
DATABASE_URL=sqlite:////opt/tap/runtime/tap.db
BACKUP_DIR=/opt/tap/runtime/backups
MEDIA_CACHE_DIR=/opt/tap/runtime/media_cache
LOG_DIR=/opt/tap/runtime/logs
CORS_ORIGINS=["https://your-domain.com"]
```
```bash
sudo chmod 600 /opt/tap/app/.env
```

> في `APP_ENV=production` يرفض التطبيق مفاتيح `CHANGE_ME` أو `JWT_SECRET_KEY` أقصر من 32 حرفًا.

### الترحيل

```bash
cd /opt/tap/app/backend
sudo -u tap /opt/tap/venv/bin/alembic upgrade head
sudo -u tap /opt/tap/venv/bin/python -c "from app.database.init_db import init_database; init_database()"
```

---

## 3. systemd

الملفات جاهزة في `deploy/systemd/` — التثبيت الآلي:

```bash
sudo ./scripts/setup_systemd.sh
sudo systemctl enable --now tap-backend tap-worker
systemctl status tap-backend tap-worker --no-pager
journalctl -u tap-worker -f        # متابعة السجلات
```

`deploy/systemd/tap-backend.service`
```ini
[Unit]
Description=Telegram Auto Publisher — FastAPI backend
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=tap
Group=tap
WorkingDirectory=/opt/tap/app/backend
EnvironmentFile=/opt/tap/app/.env
ExecStart=/opt/tap/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --proxy-headers --forwarded-allow-ips 127.0.0.1
Restart=always
RestartSec=3
LimitNOFILE=65535
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=full
ReadWritePaths=/opt/tap/runtime

[Install]
WantedBy=multi-user.target
```

`deploy/systemd/tap-worker.service`
```ini
[Unit]
Description=Telegram Auto Publisher — publishing worker (SINGLE INSTANCE)
After=network-online.target tap-backend.service
Wants=network-online.target

[Service]
Type=simple
User=tap
Group=tap
WorkingDirectory=/opt/tap/app/backend
EnvironmentFile=/opt/tap/app/.env
ExecStart=/opt/tap/venv/bin/python -m app.workers.runner
Restart=always
RestartSec=5
KillSignal=SIGTERM
TimeoutStopSec=30
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=full
ReadWritePaths=/opt/tap/runtime

[Install]
WantedBy=multi-user.target
```
> **لا تنشئ نسخة ثانية** (`@` units) من `tap-worker` — ستحصل على `database is locked` ونشر مزدوج.

---

## 4. Nginx + TLS

```bash
sudo cp deploy/nginx/telegram-auto-publisher.conf /etc/nginx/sites-available/tap.conf
sudo ln -sf /etc/nginx/sites-available/tap.conf /etc/nginx/sites-enabled/tap.conf
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx

# شهادة مجانية
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
```

الملف يقدّم: SPA من `/opt/tap/app/frontend/dist`، `proxy_pass` لـ`/api/` و`/docs` و`/openapi.json`، رؤوس أمان، gzip، و`try_files ... /index.html` لتوجيه React Router.

---

## 5. النسخ الاحتياطي المجدول (إلزامي مع SQLite)

```bash
# اختبار يدوي
cd /opt/tap/app && sudo -u tap ./scripts/backup_db.sh

# يوميًا 03:30
sudo tee /etc/systemd/system/tap-backup.service >/dev/null <<'EOF'
[Unit]
Description=Telegram Auto Publisher — SQLite online backup
[Service]
Type=oneshot
User=tap
WorkingDirectory=/opt/tap/app
ExecStart=/opt/tap/app/scripts/backup_db.sh
EOF
sudo tee /etc/systemd/system/tap-backup.timer >/dev/null <<'EOF'
[Unit]
Description=Daily TAP backup
[Timer]
OnCalendar=*-*-* 03:30:00
Persistent=true
[Install]
WantedBy=timers.target
EOF
sudo systemctl daemon-reload && sudo systemctl enable --now tap-backup.timer
systemctl list-timers tap-backup.timer
```

احتفظ بنسخة **خارج الخادم** (rsync/S3):
```bash
rsync -az /opt/tap/runtime/backups/ backup-host:/backups/tap/
```

**الاستعادة:**
```bash
sudo systemctl stop tap-worker
sudo -u tap ./scripts/restore_db.sh tap_backup_YYYYmmdd_HHMMSS_label.db
sudo systemctl start tap-worker
curl -s http://127.0.0.1:8000/api/v1/health | python3 -m json.tool
```

---

## 6. المراقبة (Monitoring)

| ما | كيف |
|---|---|
| صحة الـAPI + قاعدة البيانات | `curl -s https://your-domain.com/api/v1/health` (status=ok) |
| حالة الـWorker | لوحة المؤشرات (`worker_alive`) أو `systemctl is-active tap-worker` |
| الأخطاء | `journalctl -u tap-backend -u tap-worker -p warning --since -1h` |
| سجل عملي | `Logs` في الواجهة (فئات ERROR/CRITICAL) |
| مساحة القرص | `df -h /opt/tap` (الوسائط المؤقتة + النسخ) |
| تنبيه خارجي | مراقبة `/api/v1/health` كل دقيقة + تنبيه على `jobs_unknown > 0` |

---

## 7. الترقية (Upgrade)

```bash
cd /opt/tap/app
sudo -u tap ./scripts/backup_db.sh                    # نسخة قبل الترقية
sudo systemctl stop tap-worker
sudo -u tap git pull --ff-only
sudo -u tap /opt/tap/venv/bin/pip install -r backend/requirements.txt
sudo -u tap bash -c 'cd backend && /opt/tap/venv/bin/alembic upgrade head'
sudo -u tap bash -c 'cd frontend && npm ci && npm run build'
sudo systemctl restart tap-backend tap-worker
sudo -u tap /opt/tap/venv/bin/pytest -q -c backend/pyproject.toml backend/tests  # اختياري: تحقق
```

---

## 8. Docker Compose (اختياري)

`deploy/docker-compose.yml` يشغّل: `backend`, `worker`, `nginx` (مع بناء الواجهة)، مع volume دائم لـ`runtime/`.

```bash
cp .env.example .env && nano .env      # نفس المتغيرات، DATABASE_URL=sqlite:////data/tap.db
docker compose -f deploy/docker-compose.yml up -d --build
docker compose -f deploy/docker-compose.yml logs -f worker
```

⚠️ في Docker: **لا تزيد `replicas` للـworker**، واربط `runtime/` بـnamed volume، ولا تستخدم `bind mount` على أنظمة ملفات شبكية (SQLite WAL لا يدعمها بأمان).

---

## 9. قائمة تحقق ما قبل الإنتاج (Go-Live Checklist)

- [ ] `.env` بصلاحيات `600` خارج Git، ومفاتيح مولّدة قوية.
- [ ] `APP_ENV=production` و`CORS_ORIGINS` = النطاق الفعلي فقط.
- [ ] كلمة مرور المشرف الأول تم تغييرها من الواجهة.
- [ ] `alembic upgrade head` مُطبّق، و`/api/v1/settings/integrity` ⇒ `healthy=true`.
- [ ] `tap-backend` + `tap-worker` مُفعّلان على Boot، والـworker نسخة واحدة.
- [ ] Nginx + TLS يعمل، و`/docs` غير معرّض للعامة إن أردت (`allow/deny`).
- [ ] نسخة احتياطية يدوية ناجحة + `tap-backup.timer` مُفعّل + نسخ خارج الخادم.
- [ ] مراقبة `/api/v1/health` + تنبيه على `UNKNOWN/FAILED`.
- [ ] جدار حماية: `ufw allow 22,80,443` فقط (لا 8000/5173 للعالم).
- [ ] حساب تيليجرام مربوط، مصدر/وجهة/مسار مُختبَر فعليًا، وسجل منشورات يظهر `PUBLISHED`.
