# Telegram Auto Publisher — DATABASE.md

> SQLite (WAL) + SQLAlchemy 2.x + Alembic. المخطط الكامل، القيود، الفهارس، التشغيل، والنسخ/الاستعادة.

---

## 1. نظرة عامة

| العنصر | القيمة |
|---|---|
| المحرك | SQLite 3.35+ (Python `sqlite3` 3.46.x مُختبَر) |
| الملف | `runtime/tap.db` (يُضبط بـ`DATABASE_URL`) |
| journal_mode | `wal` (مُتحقَّق عبر `GET /api/v1/settings/integrity`) |
| Foreign keys | `ON` لكل اتصال (`PRAGMA foreign_keys=ON`) |
| busy_timeout | `5000ms` |
| synchronous | `NORMAL` (مقايضة آمنة مع WAL) |
| Migrations | Alembic — `backend/migrations/versions/0001_initial_schema_initial_schema.py` |
| الجداول | **12 جدولًا للتطبيق** (المخطط المطلوب) + `alembic_version` = **13** إجمالًا في `sqlite_master` |

---

## 2. مخطط العلاقات (ERD — نصي)

```
users ────────────┐ (actor_user_id)
                  ├──> audit_logs
telegram_accounts (singleton: حساب MTProto واحد مربوط)

source_channels ──┬──> publishing_routes ──┬──> route_filters (1:1)
                  │        │               └──> publish_jobs
                  └──> message_events ─────┬──> message_media
                                           └──> publish_jobs ──> publish_attempts

target_channels ──┬──> publishing_routes
                  └──> publish_jobs

system_settings (key/value JSON، مستقل)
```

---

## 3. الجداول (Schema)

### 3.1 `users`
| العمود | النوع | القيود |
|---|---|---|
| id | INTEGER | PK |
| username | VARCHAR(64) | UNIQUE, NOT NULL, indexed |
| email | VARCHAR(255) | UNIQUE, NOT NULL |
| password_hash | VARCHAR(255) | NOT NULL — Argon2id |
| role | VARCHAR(20) | NOT NULL, default `operator` (`admin`/`operator`) |
| is_active | BOOLEAN | NOT NULL, default 1 |
| preferred_language | VARCHAR(5) | NOT NULL, default `ar` |
| token_version | INTEGER | NOT NULL, default 1 — تُزاد لإبطال كل JWT |
| last_login_at | DATETIME | NULL |
| created_at / updated_at | DATETIME | NOT NULL |

### 3.2 `telegram_accounts` (singleton)
| العمود | النوع | ملاحظات |
|---|---|---|
| id | INTEGER | PK |
| label | VARCHAR(120) | اسم وصفي |
| api_id | INTEGER | NULL حتى الربط |
| api_hash_encrypted | TEXT | **Fernet**؛ لا يُعاد أبدًا في API |
| phone_number_encrypted | TEXT | مشفّر؛ الواجهة تعرض `masked_phone` فقط |
| encrypted_session | TEXT | **StringSession مشفّرة** |
| pending_session_encrypted | TEXT | جلسة مؤقتة أثناء OTP/2FA |
| pending_phone_code_hash | TEXT | مؤقت |
| auth_state | VARCHAR(32) | `UNCONFIGURED/DISCONNECTED/AWAITING_CODE/AWAITING_PASSWORD/CONNECTED/AUTH_ERROR` |
| telegram_user_id / telegram_username / telegram_display_name | — | بيانات الحساب بعد الربط |
| is_connected, auto_reconnect | BOOLEAN | NOT NULL |
| reconnect_attempts | INTEGER | NOT NULL, default 0 |
| last_connected_at / last_disconnected_at / heartbeat_at | DATETIME | NULL |
| last_error | TEXT | NULL |
| created_at / updated_at | DATETIME | NOT NULL |

### 3.3 `source_channels`
| العمود | النوع | ملاحظات |
|---|---|---|
| id | INTEGER | PK |
| title | VARCHAR(200) | NOT NULL |
| identifier | VARCHAR(255) | NOT NULL, UNIQUE — `@name` / رابط / peer id |
| username | VARCHAR(255) | NULL |
| telegram_peer_id | BIGINT | NULL |
| invite_link | TEXT | NULL |
| is_enabled | BOOLEAN | NOT NULL, default 1 |
| monitoring_status | VARCHAR(20) | `ACTIVE/PAUSED/UNVERIFIED/ERROR` |
| baseline_message_id | BIGINT | **نقطة البداية الموثّقة — لا أرشيف** |
| last_processed_message_id | BIGINT | NULL |
| last_processed_at | DATETIME | NULL |
| noforwards_protected | BOOLEAN | حماية المحتوى |
| access_verified_at | DATETIME | NULL |
| last_error | TEXT | NULL |
| created_at / updated_at | DATETIME | NOT NULL |

**الفهارس:** `UNIQUE(identifier)`, `ix_sources_monitoring (is_enabled, monitoring_status)`.

### 3.4 `target_channels`
| العمود | النوع | ملاحظات |
|---|---|---|
| id | INTEGER | PK |
| title | VARCHAR(200) | NOT NULL |
| identifier | VARCHAR(255) | NOT NULL, UNIQUE |
| username / telegram_peer_id / invite_link | — | NULL |
| is_enabled | BOOLEAN | NOT NULL |
| permission_status | VARCHAR(32) | `VERIFIED/INSUFFICIENT_PERMISSIONS/UNVERIFIED/ERROR` |
| can_post_messages / can_post_media | BOOLEAN | نتيجة آخر فحص فعلي |
| last_verified_at / last_test_post_at | DATETIME | NULL |
| last_error | TEXT | NULL |

### 3.5 `publishing_routes`
| العمود | النوع | ملاحظات |
|---|---|---|
| id | INTEGER | PK |
| name | VARCHAR(200) | NOT NULL |
| description | TEXT | NULL |
| source_channel_id | INTEGER | **FK → source_channels.id ON DELETE CASCADE** |
| target_channel_id | INTEGER | **FK → target_channels.id ON DELETE CASCADE** |
| is_enabled | BOOLEAN | NOT NULL، تبديل مستقل |
| priority | INTEGER | NOT NULL, default 100 |
| created_at / updated_at | DATETIME | NOT NULL |

**القيود:** `UNIQUE(source_channel_id, target_channel_id)` = `uq_route_source_target` (يمنع المسار المكرر).
**الفهارس:** `ix_routes_source_enabled (source_channel_id, is_enabled)`.

### 3.6 `route_filters` (1:1 مع المسار)
| العمود | النوع | ملاحظات |
|---|---|---|
| id | INTEGER | PK |
| route_id | INTEGER | **FK → publishing_routes.id, UNIQUE, CASCADE** |
| allowed_content_types_json | TEXT | `["text","photo","video","document","audio","voice","album"]` |
| include_keywords_json / exclude_keywords_json | TEXT | قوائم JSON |
| allowed_extensions_json | TEXT | `[".pdf", ...]` |
| min_text_length / max_text_length | INTEGER | NULL = بلا حد |
| prefix_text / suffix_text / target_signature | TEXT | NULL |
| strip_urls | BOOLEAN | default 0 |

### 3.7 `message_events` — الحدث المستلم (يُحفظ **قبل** الطابور)
| العمود | النوع | ملاحظات |
|---|---|---|
| id | INTEGER | PK |
| source_channel_id | INTEGER | **FK → source_channels.id CASCADE** |
| telegram_message_id | BIGINT | NOT NULL |
| grouped_id | VARCHAR(64) | NULL — الألبوم |
| content_type | VARCHAR(20) | `text/photo/video/document/audio/voice/album` |
| raw_text | TEXT | NULL |
| text_entities_json | TEXT | entities كما وردت |
| is_protected_content | BOOLEAN | `noforwards` |
| protection_reason | TEXT | NULL |
| album_status | VARCHAR(20) | `NONE/COLLECTING/COMPLETE/PARTIAL` |
| album_collect_until | DATETIME | نافذة التجميع |
| album_item_count | INTEGER | default 1 |
| source_published_at / received_at / enqueued_at | DATETIME | `enqueued_at` = لحظة إنشاء المهام |
| dedup_hash | VARCHAR(64) | UNIQUE, NULL — بصمة احتياطية لمنع التكرار |

**القيود:** `UNIQUE(source_channel_id, telegram_message_id)` = `uq_event_source_msg_id` — **منع التكرار الأساسي**.
**الفهارس:** `ix_events_source_grouped`, `ix_events_album_collect (album_status, album_collect_until)`, `ix_events_received_at`.

### 3.8 `message_media`
| العمود | النوع | ملاحظات |
|---|---|---|
| id | INTEGER | PK |
| message_event_id | INTEGER | **FK → message_events.id CASCADE** |
| source_channel_id | INTEGER | FK |
| telegram_message_id | BIGINT | NOT NULL |
| position | INTEGER | ترتيب العنصر داخل الألبوم (0-based) |
| media_type | VARCHAR(20) | photo/video/document/audio/voice |
| file_name / mime_type / file_ext | — | NULL |
| file_size / duration_seconds / width / height | INTEGER | NULL |
| caption | TEXT | NULL |
| status | VARCHAR(20) | `PENDING/READY/SKIPPED/FAILED` |
| error_reason | TEXT | NULL |

**القيود:** `UNIQUE(source_channel_id, telegram_message_id)` = `uq_media_source_msg_id` (لا تكرار لوسيط العنصر).
**الفهارس:** `ix_media_event_pos (message_event_id, position)`.

### 3.9 `publish_jobs` — الطابور الدائم
| العمود | النوع | ملاحظات |
|---|---|---|
| id | INTEGER | PK |
| message_event_id | INTEGER | **FK → message_events.id CASCADE** |
| route_id | INTEGER | FK → publishing_routes.id |
| source_channel_id / target_channel_id | INTEGER | FK (CASCADE) |
| status | VARCHAR(20) | `QUEUED/PROCESSING/PUBLISHED/RETRY_WAIT/SKIPPED/FAILED/UNKNOWN` |
| transformed_text | TEXT | بعد التصفية + prefix/suffix/signature |
| target_message_id | BIGINT | NULL |
| target_message_ids_json | TEXT | معرّفات الألبوم |
| attempts_count / max_attempts | INTEGER | default 0 / 4 |
| next_retry_at | DATETIME | للـ`RETRY_WAIT` |
| skip_reason / last_error / unknown_reason | TEXT | NULL |
| reconciliation_checked_at | DATETIME | NULL |
| locked_by / locked_at / heartbeat_at | — | قفل العامل ومنع الازدواج |
| published_at / created_at / updated_at | DATETIME | — |

**القيود:** `UNIQUE(message_event_id, target_channel_id)` = `uq_job_event_target` ⇒ **مهمة واحدة لكل (حدث × وجهة)** — أساس "فشل وجهة لا يعيد نشر الأخرى".
**الفهارس:** `ix_jobs_poll (status, next_retry_at, created_at)` لِـclaim، `ix_jobs_target_status`.

### 3.10 `publish_attempts`
| العمود | النوع | ملاحظات |
|---|---|---|
| id | INTEGER | PK |
| publish_job_id | INTEGER | **FK → publish_jobs.id CASCADE** |
| attempt_number | INTEGER | 1..n |
| worker_id | VARCHAR(80) | من قام بالمحاولة |
| started_at / finished_at | DATETIME | — |
| outcome | VARCHAR(20) | `IN_FLIGHT/SUCCESS/FAILED/UNKNOWN` |
| error_code / error_message | — | NULL |

**الفهارس:** `UNIQUE(publish_job_id, attempt_number)`, `ix_attempts_job`.

### 3.11 `audit_logs`
| العمود | النوع | ملاحظات |
|---|---|---|
| id | INTEGER | PK |
| level | VARCHAR(16) | `INFO/WARNING/ERROR/CRITICAL` |
| category | VARCHAR(32) | `AUTH/TELEGRAM/SOURCE/TARGET/ROUTE/INGESTION/PUBLISHER/QUEUE/BACKUP/SYSTEM/SECURITY` |
| action | VARCHAR(64) | e.g. `JOB_PUBLISHED`, `LOGIN_FAILED` |
| actor_user_id | INTEGER | FK → users.id, NULL (system) |
| actor_username | VARCHAR(64) | NULL |
| entity_type / entity_id | VARCHAR | NULL |
| message | TEXT | بلا أسرار (Redacted) |
| details_json | TEXT | JSON |
| ip_address | VARCHAR(64) | NULL |
| created_at | DATETIME | NOT NULL |

**الفهارس:** `ix_audit_category_level (category, level)`, `ix_audit_created_at`.

### 3.12 `system_settings`
| العمود | النوع | ملاحظات |
|---|---|---|
| id | INTEGER | PK |
| key | VARCHAR(100) | **UNIQUE** |
| value_json | TEXT | JSON (أي نوع) |
| category | VARCHAR(32) | general/retry/storage/security/backup/runtime |
| description | TEXT | NULL |
| updated_by | VARCHAR(64) | NULL |
| updated_at | DATETIME | NOT NULL |

**القيم الافتراضية:** `ui.default_language=ar`, `retry.max_attempts=4`, `retry.base_seconds=15`, `retry.max_seconds=900`, `album.window_ms=2500`, `storage.media_retention_hours=24`, `security.session_expire_minutes=720`, `backup.auto_before_restore=true`.

---

## 4. المعاملات (Transactions)

- كل عملية منطقية تُنفَّذ داخل معاملة واحدة تنتهي بـ`commit()` أو `rollback()`.
- استيلاء العامل على مهمة: `SELECT ... FOR UPDATE`-style منطقي (تحديث `status=PROCESSING` + `locked_by` + إنشاء `publish_attempts` في نفس المعاملة).
- لا تُترك مهمة `PROCESSING` بلا `heartbeat` أكثر من `WORKER_STALE_LOCK_TIMEOUT_SECONDS` (180s) وإلا تحوّل إلى `UNKNOWN` بواسطة الـwatchdog.

---

## 5. Alembic

```bash
cd backend
alembic upgrade head      # تطبيق كل الترحيلات
alembic downgrade base    # تراجع كامل (مُختبَر)
alembic current           # الإصدار الحالي
alembic revision --autogenerate -m "change"
```
الترحيل الأول `0001_initial_schema` ينشئ الجداول الـ12 + كل الفهارس والقيود. الاختبار `test_alembic_upgrade_and_downgrade_cycle` يتحقق من `upgrade → downgrade → upgrade`.

---

## 6. فحص السلامة

```bash
curl -s -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8000/api/v1/settings/integrity | python3 -m json.tool
```
يعيد: `healthy`, `journal_mode`, `wal_enabled`, `foreign_keys_enabled`, `integrity_check`, `foreign_key_violations`, `missing_tables`, `tables_count`.

> **ملاحظة توحيد الأرقام (مهمة):** الرقم **12** يشير دائمًا إلى جداول التطبيق المطلوبة في المواصفة.
> الرقم **13** الذي يظهر في `tables_count` و`/api/v1/health` هو نفس الـ12 **زائد** جدول Alembic الداخلي `alembic_version`.
> كلاهما صحيح ولا تناقض: عدّاد التطبيق = 12، عدّاد `sqlite_master` = 13.

مُختبَر: `test_sqlite_wal_foreign_keys_and_all_12_tables` و`test_foreign_key_and_unique_constraints_enforced`.

---

## 7. النسخ الاحتياطي والاستعادة (Online, WAL-safe)

```bash
# من الواجهة: Settings → إنشاء نسخة الآن / تنزيل / استعادة
# أو من الطرفية:
./scripts/backup_db.sh                 # ينشئ runtime/backups/tap_backup_*.db + .sha256
./scripts/restore_db.sh <filename>     # يتحقق من SHA-256 ثم يستعيد (مع نسخة أمان)
```

الآلية: `sqlite3.Connection.backup()` (نسخة متسقة أثناء التشغيل) ⇒ تحقق `PRAGMA integrity_check` ⇒ `chmod 0600` ⇒ SHA-256 ⇒ (عند الاستعادة) نسخة أمان تلقائية ثم استبدال ذرّي.

**قاعدة ذهبية للإنتاج:** لا تشغّل أكثر من Worker واحد على نفس ملف SQLite، واحتفظ بنسخ احتياطية يومية عبر `scripts/backup_db.sh` من cron/systemd timer.

---

## 8. صيانة وتنظيف

| المهمة | الأمر/الإعداد |
|---|---|
| تنظيف كاش الوسائط | تلقائي كل دورة watchdog حسب `storage.media_retention_hours` |
| ضغط الملف | `PRAGMA wal_checkpoint(TRUNCATE)` عند إيقاف الخدمة (مضمّن في سكربت النسخ) |
| فحص سلامة دوري | `GET /settings/integrity` أو `scripts/backup_db.sh` (يفحص تلقائيًا) |
| تحليل الاستعلامات | `PRAGMA optimize` (يُنفَّذ في سكربت النسخ) |
