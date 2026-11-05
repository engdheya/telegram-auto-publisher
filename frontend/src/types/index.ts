export type Language = 'ar' | 'en';

export type JobStatus =
  | 'QUEUED'
  | 'PROCESSING'
  | 'PUBLISHED'
  | 'RETRY_WAIT'
  | 'SKIPPED'
  | 'FAILED'
  | 'UNKNOWN';

export type ContentType =
  | 'text'
  | 'photo'
  | 'video'
  | 'document'
  | 'audio'
  | 'voice'
  | 'album';

export interface User {
  id: number;
  username: string;
  email: string;
  role: 'admin' | 'operator' | string;
  is_active: boolean;
  preferred_language: Language;
  last_login_at: string | null;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in_seconds: number;
  user: User;
}

export interface AuditLog {
  id: number;
  level: 'INFO' | 'WARNING' | 'ERROR' | 'CRITICAL' | string;
  category: string;
  action: string;
  actor_user_id: number | null;
  actor_username: string | null;
  entity_type: string | null;
  entity_id: string | null;
  message: string;
  details: Record<string, unknown>;
  ip_address: string | null;
  created_at: string;
}

export interface DatabaseHealth {
  healthy: boolean;
  journal_mode: string;
  wal_enabled: boolean;
  foreign_keys_enabled: boolean;
  integrity_check: string[];
  foreign_key_violations: Record<string, unknown>[];
  missing_tables: string[];
  tables_count: number;
}

export interface DashboardOverview {
  telegram_connected: boolean;
  telegram_auth_state: string;
  telegram_display_name: string | null;
  telegram_username: string | null;
  worker_alive: boolean;
  worker_last_heartbeat: string | null;
  sources_total: number;
  sources_active: number;
  targets_total: number;
  targets_verified: number;
  routes_total: number;
  routes_active: number;
  messages_received_total: number;
  jobs_published: number;
  jobs_failed: number;
  jobs_waiting: number;
  jobs_processing: number;
  jobs_skipped: number;
  jobs_unknown: number;
  database_health: DatabaseHealth;
  recent_activities: AuditLog[];
}

export interface TelegramAccountStatus {
  id: number;
  label: string;
  api_id: number | null;
  has_api_hash: boolean;
  masked_phone: string | null;
  has_saved_session: boolean;
  auth_state: string;
  telegram_user_id: number | null;
  telegram_username: string | null;
  telegram_display_name: string | null;
  is_connected: boolean;
  live_transport_connected: boolean;
  auto_reconnect: boolean;
  reconnect_attempts: number;
  last_connected_at: string | null;
  last_disconnected_at: string | null;
  heartbeat_at: string | null;
  last_error: string | null;
  updated_at: string;
}

export interface SourceChannel {
  id: number;
  title: string;
  identifier: string;
  username: string | null;
  telegram_peer_id: number | null;
  invite_link: string | null;
  is_enabled: boolean;
  monitoring_status: 'ACTIVE' | 'PAUSED' | 'UNVERIFIED' | 'ERROR' | string;
  baseline_message_id: number | null;
  last_processed_message_id: number | null;
  last_processed_at: string | null;
  noforwards_protected: boolean;
  access_verified_at: string | null;
  last_error: string | null;
  created_at: string;
  updated_at: string;
}

export interface TargetChannel {
  id: number;
  title: string;
  identifier: string;
  username: string | null;
  telegram_peer_id: number | null;
  invite_link: string | null;
  is_enabled: boolean;
  permission_status: 'VERIFIED' | 'INSUFFICIENT_PERMISSIONS' | 'UNVERIFIED' | 'ERROR' | string;
  can_post_messages: boolean;
  can_post_media: boolean;
  last_verified_at: string | null;
  last_test_post_at: string | null;
  last_error: string | null;
  created_at: string;
  updated_at: string;
}

export interface RouteFilterConfig {
  allowed_content_types: ContentType[];
  include_keywords: string[];
  exclude_keywords: string[];
  allowed_extensions: string[];
  min_text_length: number | null;
  max_text_length: number | null;
  prefix_text: string | null;
  suffix_text: string | null;
  target_signature: string | null;
  strip_urls: boolean;
}

export interface PublishingRoute {
  id: number;
  name: string;
  description: string | null;
  source_channel_id: number;
  source_title: string;
  source_identifier: string;
  target_channel_id: number;
  target_title: string;
  target_identifier: string;
  is_enabled: boolean;
  priority: number;
  filters: RouteFilterConfig;
  created_at: string;
  updated_at: string;
}

export interface MessageMedia {
  id: number;
  telegram_message_id: number;
  position: number;
  media_type: string;
  file_name: string | null;
  mime_type: string | null;
  file_ext: string | null;
  file_size: number | null;
  duration_seconds: number | null;
  width: number | null;
  height: number | null;
  caption: string | null;
  status: string;
  error_reason: string | null;
}

export interface PublishAttempt {
  id: number;
  attempt_number: number;
  worker_id: string;
  started_at: string;
  finished_at: string | null;
  outcome: string;
  error_code: string | null;
  error_message: string | null;
}

export interface PublishJobSummary {
  id: number;
  message_event_id: number;
  route_id: number;
  route_name: string;
  source_channel_id: number;
  source_title: string;
  target_channel_id: number;
  target_title: string;
  status: JobStatus;
  transformed_text: string | null;
  target_message_id: number | null;
  target_message_ids: number[];
  attempts_count: number;
  max_attempts: number;
  next_retry_at: string | null;
  skip_reason: string | null;
  last_error: string | null;
  unknown_reason: string | null;
  reconciliation_checked_at: string | null;
  published_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface PublishJobDetail extends PublishJobSummary {
  content_type: string;
  raw_text: string | null;
  grouped_id: string | null;
  album_item_count: number;
  attempts: PublishAttempt[];
}

export interface MessageEventItem {
  id: number;
  source_channel_id: number;
  source_title: string;
  telegram_message_id: number;
  grouped_id: string | null;
  content_type: string;
  raw_text: string | null;
  is_protected_content: boolean;
  protection_reason: string | null;
  album_status: string;
  album_item_count: number;
  source_published_at: string | null;
  received_at: string;
  enqueued_at: string | null;
  media_items: MessageMedia[];
  jobs: PublishJobSummary[];
}

export interface SystemSettingItem {
  key: string;
  value: unknown;
  category: string;
  description: string | null;
  updated_by: string | null;
  updated_at: string | null;
}

export interface BackupItem {
  filename: string;
  size_bytes: number;
  sha256: string | null;
  created_at: string;
}
