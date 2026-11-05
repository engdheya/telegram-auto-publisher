# Telegram Auto Publisher — API.md

> REST API v1 · Base URL: `http://<host>:8000/api/v1` · OpenAPI/Swagger: `/docs` · Schema: `/openapi.json`
> كل المسارات (ما عدا `/login` و`/health`) تتطلب `Authorization: Bearer <JWT>`.
> الاستجابات الخطأ موحّدة: `{ "detail": "message", "code": "ERROR_CODE" }`.

---

## 0. المصادقة (Auth)

### POST `/auth/login`
```json
{ "username": "admin", "password": "<ADMIN_PASSWORD>" }
```
**200**
```json
{ "access_token": "eyJhbGciOi...", "token_type": "bearer", "expires_in_seconds": 43200,
  "user": { "id":1,"username":"admin","email":"admin@tap.local","role":"admin","is_active":true,"preferred_language":"ar","last_login_at":null,"created_at":"..." } }
```
**401** `{"detail":"Invalid username or password.","code":"AUTH_INVALID_CREDENTIALS"}`

| Method | Path | الوصف | صلاحية |
|---|---|---|---|
| GET | `/auth/me` | بيانات المستخدم الحالي | أي مستخدم |
| POST | `/auth/change-password` | `{current_password,new_password}` ⇒ JWT جديد، إبطال القديم | أي مستخدم |
| PATCH | `/auth/language` | `{preferred_language:"ar"\|"en"}` | أي مستخدم |
| GET | `/auth/users` | قائمة المستخدمين | admin |
| POST | `/auth/users` | `{username,email,password,role,preferred_language}` | admin |

---

## 1. Dashboard

### GET `/dashboard/overview`
```json
{ "telegram_connected": true, "telegram_auth_state": "CONNECTED", "telegram_display_name":"...", "telegram_username":"...",
  "worker_alive": true, "worker_last_heartbeat": "2026-11-05T21:06:54Z",
  "sources_total": 4, "sources_active": 3, "targets_total": 2, "targets_verified": 2,
  "routes_total": 9, "routes_active": 8, "messages_received_total": 120,
  "jobs_published": 98, "jobs_failed": 1, "jobs_waiting": 2, "jobs_processing": 0, "jobs_skipped": 15, "jobs_unknown": 0,
  "database_health": { "healthy": true, "journal_mode": "wal", "wal_enabled": true, "foreign_keys_enabled": true,
                       "integrity_check": ["ok"], "foreign_key_violations": [], "missing_tables": [], "tables_count": 13 },
  "recent_activities": [ { "id": 42, "level": "INFO", "category": "PUBLISHER", "action": "JOB_PUBLISHED", "...": "..." } ] }
```

---

## 2. Telegram Account

| Method | Path | الوصف | صلاحية |
|---|---|---|---|
| GET | `/telegram/status` | حالة الحساب (بلا أسرار) | مستخدم |
| POST | `/telegram/send-code` | `{label?,api_id,api_hash,phone_number,auto_reconnect?}` ⇒ إرسال OTP | admin |
| POST | `/telegram/verify-code` | `{code,password?}` ⇒ `CONNECTED` أو `AWAITING_PASSWORD` | admin |
| POST | `/telegram/verify-password` | `{password}` ⇒ 2FA | admin |
| POST | `/telegram/reconnect` | إعادة اتصال الجلسة المحفوظة + catch-up | admin |
| PATCH | `/telegram/auto-reconnect` | `{auto_reconnect: bool}` | admin |
| POST | `/telegram/logout` | حذف الجلسة وإلغاء الربط | admin |

**200 (status)**
```json
{ "id":1, "label":"Primary Telegram Account", "api_id":1234567, "has_api_hash":true,
  "masked_phone":"+967******000", "has_saved_session":true, "auth_state":"CONNECTED",
  "telegram_user_id":777, "telegram_username":"my_account", "telegram_display_name":"My Name",
  "is_connected":true, "live_transport_connected":true, "auto_reconnect":true, "reconnect_attempts":0,
  "last_connected_at":"...", "last_disconnected_at":null, "heartbeat_at":"...", "last_error":null, "updated_at":"..." }
```
> **لا يُعاد `api_hash` ولا الجلسة أبدًا.** عند عدم وجود جلسة: `auth_state="UNCONFIGURED"`.

---

## 3. Sources

| Method | Path | Body/Params | الوصف |
|---|---|---|---|
| GET | `/sources` | — | كل المصادر |
| POST | `/sources` | `{title,identifier,invite_link?,is_enabled?}` | إنشاء (UNIQUE identifier ⇒ 409) |
| PATCH | `/sources/{id}` | أي من `{title,identifier,invite_link,is_enabled}` | تعديل |
| DELETE | `/sources/{id}` | — | حذف (CASCADE على المسارات) |
| POST | `/sources/{id}/verify` | — | فحص الوصول عبر Telethon |
| POST | `/sources/{id}/start` | — | بدء المراقبة + تسجيل baseline |
| POST | `/sources/{id}/stop` | — | إيقاف المراقبة |

**Source object**
```json
{ "id":1,"title":"Test Source","identifier":"@test_source","username":"test_source","telegram_peer_id":null,
  "invite_link":null,"is_enabled":true,"monitoring_status":"ACTIVE","baseline_message_id":512,
  "last_processed_message_id":520,"last_processed_at":"...","noforwards_protected":false,
  "access_verified_at":"...","last_error":null,"created_at":"...","updated_at":"..." }
```
**verify ⇒ 200**
```json
{ "accessible": true, "source": { "...": "..." }, "detail": "Access verified. baseline_message_id=512" }
```
إن لم يكن الحساب متصلًا: `{"accessible": false, "detail": "Telegram client is not connected...", "source": {"monitoring_status":"ERROR", "last_error":"..."}}`

---

## 4. Targets

| Method | Path | Body | الوصف |
|---|---|---|---|
| GET | `/targets` | — | كل الوجهات |
| POST | `/targets` | `{title,identifier,invite_link?,is_enabled?}` | إنشاء |
| PATCH | `/targets/{id}` | جزئي | تعديل |
| DELETE | `/targets/{id}` | — | حذف |
| POST | `/targets/{id}/verify` | — | فحص `can_post_messages/media` |
| POST | `/targets/{id}/test-publish` | `{message?}` | **نشر رسالة حقيقية** |

**test-publish ⇒ 200**
```json
{ "ok": false, "target": {"permission_status":"INSUFFICIENT_PERMISSIONS","can_post_messages":false,"...":"..."},
  "detail": "ChatWriteForbiddenError: not enough rights to send text messages to the chat", "test_message_id": null }
```

---

## 5. Routes

| Method | Path | Body | الوصف |
|---|---|---|---|
| GET | `/routes?source_id=&target_id=` | — | قائمة المسارات مع الفلاتر |
| POST | `/routes` | `PublishingRouteCreate` | مسار واحد |
| POST | `/routes/bulk` | `{name_prefix,source_channel_ids[],target_channel_ids[],is_enabled?,filters?}` | **N×M ذرّي** (تخطي المكرر) |
| PATCH | `/routes/{id}` | `{name?,description?,is_enabled?,priority?,filters?}` | تعديل |
| POST | `/routes/{id}/toggle` | — | تبديل مستقل |
| DELETE | `/routes/{id}` | — | حذف |

```json
// PublishingRouteCreate
{ "name":"Source A → Target 1", "description":null, "source_channel_id":1, "target_channel_id":2,
  "is_enabled":true, "priority":100,
  "filters": { "allowed_content_types":["text","photo","video","document","audio","voice","album"],
               "include_keywords":[], "exclude_keywords":["promo"], "allowed_extensions":[".pdf"],
               "min_text_length":null, "max_text_length":null,
               "prefix_text":"📌 ", "suffix_text":null, "target_signature":"@my_channel", "strip_urls":false } }
```
**Response (PublishingRoute)**
```json
{ "id":9,"name":"...","description":null,"source_channel_id":1,"source_title":"Test Source","source_identifier":"@test_source",
  "target_channel_id":2,"target_title":"Test Target","target_identifier":"@test_target",
  "is_enabled":true,"priority":100,"filters":{ "...": "..." },"created_at":"...","updated_at":"..." }
```

---

## 6. Messages (Publishing History)

### GET `/messages?page=1&page_size=20&source_id=&content_type=&search=`
```json
{ "total": 120, "page": 1, "page_size": 20,
  "items": [ { "id":51,"source_channel_id":1,"source_title":"Test Source","telegram_message_id":512,
               "grouped_id":"4412...","content_type":"album","raw_text":"caption",
               "is_protected_content":false,"protection_reason":null,"album_status":"COMPLETE","album_item_count":3,
               "source_published_at":"...","received_at":"...","enqueued_at":"...",
               "media_items":[{"id":1,"telegram_message_id":512,"position":0,"media_type":"photo","file_name":null,"mime_type":"image/jpeg","file_ext":".jpg","file_size":204800,"duration_seconds":null,"width":1280,"height":720,"caption":null,"status":"READY","error_reason":null}],
               "jobs":[{"id":101,"message_event_id":51,"route_id":9,"route_name":"...","source_channel_id":1,"source_title":"...","target_channel_id":2,"target_title":"...","status":"PUBLISHED","transformed_text":"...","target_message_id":903,"target_message_ids":[901,902,903],"attempts_count":1,"max_attempts":4,"next_retry_at":null,"skip_reason":null,"last_error":null,"unknown_reason":null,"reconciliation_checked_at":null,"published_at":"...","created_at":"...","updated_at":"..."}] } ] }
```
`GET /messages/{event_id}` يعيد نفس الكائن لحدث واحد.

---

## 7. Queue Management

| Method | Path | Params | الوصف |
|---|---|---|---|
| GET | `/queue/jobs` | `page,page_size,status,target_id,source_id` | `counts_by_status` + `items` (تفاصيل كاملة + attempts) |
| GET | `/queue/jobs/{id}` | — | مهمة واحدة |
| POST | `/queue/jobs/{id}/retry` | — | إعادة محاولة آمنة (ترفض `PROCESSING`/`PUBLISHED`) |
| POST | `/queue/jobs/{id}/reconcile` | `requeue_if_missing=true` | **مصالحة UNKNOWN** قبل الإعادة |
| POST | `/queue/jobs/{id}/cancel` | — | تحويل إلى `SKIPPED` (لا يجوز لـ`PUBLISHED`/`PROCESSING`) |

```json
// GET /queue/jobs?status=FAILED
{ "total":1,"page":1,"page_size":25,
  "counts_by_status":{"QUEUED":0,"PROCESSING":0,"PUBLISHED":98,"RETRY_WAIT":0,"SKIPPED":15,"FAILED":1,"UNKNOWN":0},
  "items":[ { "id":101,"status":"FAILED","last_error":"ChatWriteForbiddenError...","attempts":[
      {"id":7,"attempt_number":1,"worker_id":"tap-primary-worker","started_at":"...","finished_at":"...","outcome":"FAILED","error_code":"RPC_ERROR","error_message":"..."} ],
      "content_type":"text","raw_text":"...","grouped_id":null,"album_item_count":1, "...": "..." } ] }
```
**QueueActionResponse**
```json
{ "ok": true, "detail": "Job #101 re-queued as QUEUED.", "job": { "...": "..." } }
```

---

## 8. Logs

### GET `/logs?page=1&page_size=30&level=ERROR&category=PUBLISHER&search=text`
```json
{ "total": 3, "page":1, "page_size":30,
  "items":[ {"id":42,"level":"ERROR","category":"PUBLISHER","action":"JOB_FAILED","actor_user_id":null,"actor_username":"system",
             "entity_type":"publish_job","entity_id":"101","message":"...","details":{"error":"..."},"ip_address":null,"created_at":"..."} ] }
```

---

## 9. Settings, Integrity & Backups

| Method | Path | Body | صلاحية |
|---|---|---|---|
| GET | `/settings` | — | مستخدم |
| PUT | `/settings` | `{settings:[{key,value}, ...]}` | admin |
| GET | `/settings/integrity` | — | مستخدم |
| GET | `/settings/backups` | — | admin |
| POST | `/settings/backups` | `{label?}` | admin |
| GET | `/settings/backups/{filename}/download` | — | admin (ملف SQLite) |
| POST | `/settings/backups/restore` | `{filename}` | admin |

```json
// GET /settings
{ "items": [ {"key":"retry.max_attempts","value":4,"category":"retry","description":"...","updated_by":"system","updated_at":"..."} ] }

// POST /settings/backups
{ "filename":"tap_backup_20261105_205210_016428_smoke.db","size_bytes":98304,"sha256":"3465503ac161d27a...","created_at":"..." }

// POST /settings/backups/restore
{ "restored_from":"tap_backup_...db","sha256":"...","pre_restore_backup":"tap_backup_..._prerestore.db","restored_at":"..." }
```

---

## 10. Health

`GET /health` (بلا مصادقة):
```json
{ "status":"ok", "version":"1.0.0", "database":{"healthy":true,"journal_mode":"wal","wal_enabled":true,"foreign_keys_enabled":true,"integrity_check":["ok"],"foreign_key_violations":[],"missing_tables":[],"tables_count":13} }
```

---

## 11. رموز الأخطاء الشائعة

| HTTP | code | المعنى |
|---|---|---|
| 401 | `AUTH_INVALID_CREDENTIALS` / `AUTH_TOKEN_INVALID` | بيانات دخول خاطئة أو JWT منتهٍ/مُبطَل |
| 403 | `AUTH_FORBIDDEN` | الصلاحية غير كافية (operator لعملية admin) |
| 404 | `RESOURCE_NOT_FOUND` | كيان غير موجود |
| 409 | `CONFLICT` | تكرار (`identifier` أو مسار مكرر) |
| 422 | (FastAPI) | فشل تحقق الحقول |
| 500 | `INTERNAL_ERROR` | خطأ غير متوقع (يُسجَّل بلا أسرار) |

---

## 12. أمثلة cURL

```bash
BASE=http://127.0.0.1:8000/api/v1
TOKEN=$(curl -s -X POST $BASE/auth/login -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"<ADMIN_PASSWORD>"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')
AUTH="Authorization: Bearer $TOKEN"

curl -s -H "$AUTH" $BASE/dashboard/overview | python3 -m json.tool
curl -s -X POST -H "$AUTH" -H 'Content-Type: application/json' -d '{"title":"Source A","identifier":"@source_a"}' $BASE/sources
curl -s -X POST -H "$AUTH" -H 'Content-Type: application/json' \
     -d '{"name_prefix":"Route","source_channel_ids":[1],"target_channel_ids":[2,3],"is_enabled":true}' $BASE/routes/bulk
curl -s -H "$AUTH" "$BASE/queue/jobs?status=FAILED" | python3 -m json.tool
curl -s -X POST -H "$AUTH" "$BASE/queue/jobs/101/reconcile?requeue_if_missing=true"
curl -s -X POST -H "$AUTH" -H 'Content-Type: application/json' -d '{"label":"nightly"}' $BASE/settings/backups
```
