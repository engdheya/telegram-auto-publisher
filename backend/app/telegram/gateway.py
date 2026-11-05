"""Normalized incoming/outgoing Telegram structures and live Telethon MTProto gateway."""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from telethon import TelegramClient, errors as tg_errors, utils as tg_utils
from telethon.sessions import StringSession
from telethon.tl import types as tl_types

from app.core.config import get_settings
from app.core.exceptions import (
    AmbiguousPublishError,
    PermanentPublishError,
    TelegramOperationError,
    TransientPublishError,
)
from app.telegram.formatter import deserialize_entities, serialize_entities
from app.utils.media import normalize_extension, safe_filename
from app.utils.time import utcnow


@dataclass
class IncomingMediaItem:
    telegram_message_id: int
    media_type: str  # photo | video | document | audio | voice
    file_name: str | None = None
    mime_type: str | None = None
    file_ext: str | None = None
    file_size: int | None = None
    duration_seconds: int | None = None
    width: int | None = None
    height: int | None = None
    caption: str | None = None
    caption_entities: list[dict[str, Any]] = field(default_factory=list)
    local_cache_path: str | None = None


@dataclass
class IncomingTelegramEvent:
    source_peer_id: int | None
    source_identifier: str | None
    telegram_message_id: int
    grouped_id: str | None
    content_type: str  # text | photo | video | document | audio | voice | unsupported
    raw_text: str | None
    entities: list[dict[str, Any]]
    is_protected_content: bool
    protection_reason: str | None
    published_at: datetime
    is_edit: bool = False
    media: IncomingMediaItem | None = None


@dataclass
class TargetRecentPost:
    message_id: int
    text: str
    published_at: datetime
    has_media: bool
    media_count: int = 1


class TelegramGatewayProtocol(Protocol):
    """Protocol implemented by both live TelethonClientManager and deterministic test simulator."""

    def is_live_connected(self) -> bool: ...

    async def send_login_code(
        self, api_id: int, api_hash: str, phone_number: str
    ) -> tuple[str, str]: ...

    async def verify_code(
        self,
        api_id: int,
        api_hash: str,
        pending_session: str,
        phone_number: str,
        code: str,
        phone_code_hash: str,
        password: str | None = None,
    ) -> dict[str, Any]: ...

    async def verify_2fa_password(
        self, api_id: int, api_hash: str, pending_session: str, password: str
    ) -> dict[str, Any]: ...

    async def connect_saved_session(self, api_id: int, api_hash: str, session_str: str) -> dict[str, Any]: ...

    async def disconnect_and_logout(
        self, api_id: int | None, api_hash: str | None, session_str: str | None, revoke: bool = True
    ) -> None: ...

    async def inspect_source_channel(self, identifier: str) -> dict[str, Any]: ...

    async def inspect_target_channel(self, identifier: str) -> dict[str, Any]: ...

    async def send_target_test_message(self, identifier: str, text: str) -> int: ...

    async def fetch_missed_messages(
        self, identifier_or_peer: str | int, min_message_id: int, limit: int = 100
    ) -> list[IncomingTelegramEvent]: ...

    async def publish_job_payload(
        self,
        *,
        target_identifier: str | int,
        source_identifier: str | int,
        content_type: str,
        text: str,
        entities_json: str,
        source_message_ids: list[int],
        media_descriptors: list[dict[str, Any]],
    ) -> list[int]: ...

    async def fetch_recent_target_posts(
        self, target_identifier: str | int, limit: int = 20
    ) -> list[TargetRecentPost]: ...


def extract_incoming_event_from_telethon_message(
    msg: tl_types.Message,
    chat: Any = None,
) -> IncomingTelegramEvent:
    """Convert a live Telethon Message into a normalized IncomingTelegramEvent."""
    peer_id = tg_utils.get_peer_id(msg.peer_id) if getattr(msg, "peer_id", None) else None
    username = getattr(chat, "username", None)
    identifier = f"@{username}" if username else (str(peer_id) if peer_id else None)

    chat_noforwards = bool(getattr(chat, "noforwards", False))
    msg_noforwards = bool(getattr(msg, "noforwards", False))
    protected = chat_noforwards or msg_noforwards
    protection_reason = (
        "PROTECTED_CONTENT_NOFORWARDS: Source channel or post restricts forwarding/copying."
        if protected
        else None
    )

    entities = serialize_entities(getattr(msg, "entities", None))
    raw_text = getattr(msg, "message", None) or ""
    grouped_id = str(msg.grouped_id) if getattr(msg, "grouped_id", None) else None
    pub_dt = getattr(msg, "date", None) or utcnow()
    is_edit = getattr(msg, "edit_date", None) is not None

    content_type = "text"
    media_item: IncomingMediaItem | None = None

    if getattr(msg, "photo", None):
        content_type = "photo"
        media_item = IncomingMediaItem(
            telegram_message_id=msg.id,
            media_type="photo",
            file_name=f"photo_{msg.id}.jpg",
            mime_type="image/jpeg",
            file_ext=".jpg",
            caption=raw_text or None,
            caption_entities=entities,
        )
    elif getattr(msg, "document", None):
        doc = msg.document
        mime = getattr(doc, "mime_type", None) or "application/octet-stream"
        size = getattr(doc, "size", None)
        fname = None
        duration = None
        width = None
        height = None
        is_voice = False
        is_audio = False
        is_video = False

        for attr in getattr(doc, "attributes", []) or []:
            if isinstance(attr, tl_types.DocumentAttributeFilename):
                fname = attr.file_name
            elif isinstance(attr, tl_types.DocumentAttributeVideo):
                is_video = True
                duration = int(getattr(attr, "duration", 0) or 0)
                width = getattr(attr, "w", None)
                height = getattr(attr, "h", None)
            elif isinstance(attr, tl_types.DocumentAttributeAudio):
                duration = int(getattr(attr, "duration", 0) or 0)
                if getattr(attr, "voice", False):
                    is_voice = True
                else:
                    is_audio = True

        if is_voice:
            content_type = "voice"
        elif is_video or mime.startswith("video/"):
            content_type = "video"
        elif is_audio or mime.startswith("audio/"):
            content_type = "audio"
        else:
            content_type = "document"

        ext = normalize_extension(fname, mime)
        media_item = IncomingMediaItem(
            telegram_message_id=msg.id,
            media_type=content_type,
            file_name=fname or f"{content_type}_{msg.id}{ext}",
            mime_type=mime,
            file_ext=ext,
            file_size=size,
            duration_seconds=duration,
            width=width,
            height=height,
            caption=raw_text or None,
            caption_entities=entities,
        )
    elif getattr(msg, "media", None) and not isinstance(msg.media, tl_types.MessageMediaWebPage):
        content_type = "unsupported"

    return IncomingTelegramEvent(
        source_peer_id=peer_id,
        source_identifier=identifier,
        telegram_message_id=int(msg.id),
        grouped_id=grouped_id,
        content_type=content_type,
        raw_text=raw_text,
        entities=entities,
        is_protected_content=protected,
        protection_reason=protection_reason,
        published_at=pub_dt,
        is_edit=is_edit,
        media=media_item,
    )


def _normalize_target_identifier(identifier: str | int) -> str | int:
    if isinstance(identifier, int):
        return identifier
    cleaned = identifier.strip()
    for prefix in ("https://t.me/", "http://t.me/", "t.me/"):
        if cleaned.lower().startswith(prefix):
            slug = cleaned[len(prefix) :].strip("/")
            if slug and not slug.startswith("+") and not slug.startswith("joinchat"):
                return f"@{slug}"
            return cleaned
    if cleaned.lstrip("-").isdigit():
        return int(cleaned)
    return cleaned


class TelethonClientManager:
    """
    Production Telethon MTProto client manager supporting StringSession encryption,
    automatic reconnection, channel permission checks, media/album publishing, and reconciliation.
    """

    def __init__(self) -> None:
        self._client: TelegramClient | None = None
        self._active_api_id: int | None = None
        self._active_api_hash: str | None = None
        self._active_session_str: str | None = None

    def get_raw_client(self) -> TelegramClient | None:
        return self._client

    def is_live_connected(self) -> bool:
        return bool(self._client and self._client.is_connected())

    def _create_ephemeral_client(self, api_id: int, api_hash: str, session_str: str = "") -> TelegramClient:
        return TelegramClient(
            StringSession(session_str or None),
            api_id,
            api_hash,
            connection_retries=3,
            retry_delay=2,
            auto_reconnect=True,
            device_model="TelegramAutoPublisher Server",
            system_version="Ubuntu Linux",
            app_version="1.0.0",
        )

    async def send_login_code(
        self, api_id: int, api_hash: str, phone_number: str
    ) -> tuple[str, str]:
        client = self._create_ephemeral_client(api_id, api_hash)
        await client.connect()
        try:
            sent = await client.send_code_request(phone_number)
            pending_session = client.session.save()
            return pending_session, sent.phone_code_hash
        except tg_errors.ApiIdInvalidError as exc:
            raise TelegramOperationError("Invalid Telegram API ID or API Hash.", code="API_ID_INVALID") from exc
        except tg_errors.PhoneNumberInvalidError as exc:
            raise TelegramOperationError("Invalid phone number format.", code="PHONE_INVALID") from exc
        except tg_errors.FloodWaitError as exc:
            raise TelegramOperationError(
                f"Telegram rate limit: please wait {exc.seconds} seconds.", code="FLOOD_WAIT", status_code=429
            ) from exc
        except Exception as exc:
            raise TelegramOperationError(f"Failed to request login code: {type(exc).__name__}") from exc
        finally:
            await client.disconnect()

    async def verify_code(
        self,
        api_id: int,
        api_hash: str,
        pending_session: str,
        phone_number: str,
        code: str,
        phone_code_hash: str,
        password: str | None = None,
    ) -> dict[str, Any]:
        client = self._create_ephemeral_client(api_id, api_hash, pending_session)
        await client.connect()
        try:
            try:
                user = await client.sign_in(
                    phone=phone_number,
                    code=code.strip(),
                    phone_code_hash=phone_code_hash,
                )
            except tg_errors.SessionPasswordNeededError:
                if not password:
                    saved_pending = client.session.save()
                    await client.disconnect()
                    return {
                        "state": "AWAITING_PASSWORD",
                        "pending_session": saved_pending,
                    }
                user = await client.sign_in(password=password)

            final_session = client.session.save()
            info = self._extract_user_info(user)
            await self._adopt_connected_client(client, api_id, api_hash, final_session)
            return {
                "state": "CONNECTED",
                "session_str": final_session,
                **info,
            }
        except tg_errors.PhoneCodeInvalidError as exc:
            await client.disconnect()
            raise TelegramOperationError("Invalid Telegram verification code.", code="CODE_INVALID") from exc
        except tg_errors.PhoneCodeExpiredError as exc:
            await client.disconnect()
            raise TelegramOperationError("Verification code expired; request a new code.", code="CODE_EXPIRED") from exc
        except tg_errors.PasswordHashInvalidError as exc:
            await client.disconnect()
            raise TelegramOperationError("Invalid 2FA cloud password.", code="PASSWORD_INVALID") from exc
        except Exception as exc:
            await client.disconnect()
            raise TelegramOperationError(f"Telegram sign-in failed: {type(exc).__name__}") from exc

    async def verify_2fa_password(
        self, api_id: int, api_hash: str, pending_session: str, password: str
    ) -> dict[str, Any]:
        client = self._create_ephemeral_client(api_id, api_hash, pending_session)
        await client.connect()
        try:
            user = await client.sign_in(password=password)
            final_session = client.session.save()
            info = self._extract_user_info(user)
            await self._adopt_connected_client(client, api_id, api_hash, final_session)
            return {
                "state": "CONNECTED",
                "session_str": final_session,
                **info,
            }
        except tg_errors.PasswordHashInvalidError as exc:
            await client.disconnect()
            raise TelegramOperationError("Invalid 2FA cloud password.", code="PASSWORD_INVALID") from exc
        except Exception as exc:
            await client.disconnect()
            raise TelegramOperationError(f"2FA sign-in failed: {type(exc).__name__}") from exc

    async def connect_saved_session(self, api_id: int, api_hash: str, session_str: str) -> dict[str, Any]:
        if (
            self._client
            and self._client.is_connected()
            and self._active_session_str == session_str
            and self._active_api_id == api_id
        ):
            me = await self._client.get_me()
            if me:
                return self._extract_user_info(me)

        client = TelegramClient(
            StringSession(session_str),
            api_id,
            api_hash,
            connection_retries=None,
            retry_delay=5,
            auto_reconnect=True,
            device_model="TelegramAutoPublisher Server",
            system_version="Ubuntu Linux",
            app_version="1.0.0",
        )
        await client.connect()
        if not await client.is_user_authorized():
            await client.disconnect()
            raise TelegramOperationError(
                "Saved Telegram session is no longer authorized. Please log in again.",
                code="SESSION_REVOKED",
                status_code=401,
            )
        me = await client.get_me()
        await self._adopt_connected_client(client, api_id, api_hash, session_str)
        return self._extract_user_info(me)

    async def _adopt_connected_client(
        self, client: TelegramClient, api_id: int, api_hash: str, session_str: str
    ) -> None:
        if self._client and self._client is not client:
            try:
                await self._client.disconnect()
            except Exception:
                pass
        self._client = client
        self._active_api_id = api_id
        self._active_api_hash = api_hash
        self._active_session_str = session_str

    async def disconnect_and_logout(
        self, api_id: int | None, api_hash: str | None, session_str: str | None, revoke: bool = True
    ) -> None:
        if self._client:
            try:
                if revoke and self._client.is_connected():
                    await self._client.log_out()
                else:
                    await self._client.disconnect()
            except Exception:
                try:
                    await self._client.disconnect()
                except Exception:
                    pass
            finally:
                self._client = None
                self._active_session_str = None
        elif revoke and api_id and api_hash and session_str:
            temp = self._create_ephemeral_client(api_id, api_hash, session_str)
            try:
                await temp.connect()
                if await temp.is_user_authorized():
                    await temp.log_out()
            except Exception:
                pass
            finally:
                await temp.disconnect()

    def _require_client(self) -> TelegramClient:
        if not self._client or not self._client.is_connected():
            raise TelegramOperationError(
                "Telegram client is not connected. Connect your Telegram account first.",
                code="TELEGRAM_NOT_CONNECTED",
                status_code=400,
            )
        return self._client

    @staticmethod
    def _extract_user_info(user: Any) -> dict[str, Any]:
        first = getattr(user, "first_name", "") or ""
        last = getattr(user, "last_name", "") or ""
        display = f"{first} {last}".strip() or getattr(user, "username", None) or f"User {user.id}"
        return {
            "telegram_user_id": int(user.id),
            "telegram_username": getattr(user, "username", None),
            "telegram_display_name": display,
        }

    async def inspect_source_channel(self, identifier: str) -> dict[str, Any]:
        client = self._require_client()
        ref = _normalize_target_identifier(identifier)
        try:
            entity = await client.get_entity(ref)
            peer_id = tg_utils.get_peer_id(entity)
            title = getattr(entity, "title", None) or getattr(entity, "username", None) or str(identifier)
            username = getattr(entity, "username", None)
            noforwards = bool(getattr(entity, "noforwards", False))

            # Fetch ONLY the single latest message ID to document baseline without importing archive!
            msgs = await client.get_messages(entity, limit=1)
            latest_id = int(msgs[0].id) if msgs and len(msgs) > 0 else 0

            return {
                "accessible": True,
                "peer_id": int(peer_id),
                "title": title,
                "username": username,
                "noforwards": noforwards,
                "latest_message_id": latest_id,
            }
        except (tg_errors.ChannelPrivateError, tg_errors.ChatAdminRequiredError) as exc:
            raise TelegramOperationError(
                f"Cannot access source channel ({type(exc).__name__}): account is not a member or lacks access.",
                code="SOURCE_ACCESS_DENIED",
            ) from exc
        except ValueError as exc:
            raise TelegramOperationError(f"Channel '{identifier}' could not be resolved.", code="CHANNEL_NOT_FOUND") from exc
        except Exception as exc:
            raise TelegramOperationError(f"Source verification failed: {type(exc).__name__}: {exc}") from exc

    async def inspect_target_channel(self, identifier: str) -> dict[str, Any]:
        client = self._require_client()
        ref = _normalize_target_identifier(identifier)
        try:
            entity = await client.get_entity(ref)
            peer_id = tg_utils.get_peer_id(entity)
            title = getattr(entity, "title", None) or getattr(entity, "username", None) or str(identifier)
            username = getattr(entity, "username", None)

            can_post = False
            can_media = False
            if getattr(entity, "creator", False):
                can_post = True
                can_media = True
            else:
                admin_rights = getattr(entity, "admin_rights", None)
                if admin_rights and getattr(admin_rights, "post_messages", False):
                    can_post = True
                    can_media = True
                elif not getattr(entity, "broadcast", False):
                    perms = await client.get_permissions(entity, "me")
                    can_post = bool(getattr(perms, "send_messages", False))
                    can_media = bool(getattr(perms, "send_media", can_post))
                else:
                    perms = await client.get_permissions(entity, "me")
                    can_post = bool(getattr(perms, "post_messages", False) or getattr(perms, "is_creator", False))
                    can_media = can_post

            return {
                "peer_id": int(peer_id),
                "title": title,
                "username": username,
                "can_post_messages": can_post,
                "can_post_media": can_media,
            }
        except (tg_errors.ChannelPrivateError, ValueError) as exc:
            raise TelegramOperationError(
                f"Cannot resolve or access target channel '{identifier}': {type(exc).__name__}",
                code="TARGET_NOT_ACCESSIBLE",
            ) from exc
        except Exception as exc:
            raise TelegramOperationError(f"Target verification failed: {type(exc).__name__}: {exc}") from exc

    async def send_target_test_message(self, identifier: str, text: str) -> int:
        client = self._require_client()
        ref = _normalize_target_identifier(identifier)
        try:
            sent = await client.send_message(ref, text)
            return int(sent.id)
        except (tg_errors.ChatWriteForbiddenError, tg_errors.ChatAdminRequiredError, tg_errors.UserBannedInChannelError) as exc:
            raise TelegramOperationError(
                f"Publishing forbidden in target channel ({type(exc).__name__}). Ensure account is an admin with 'Post Messages' permission.",
                code="TARGET_WRITE_FORBIDDEN",
                status_code=403,
            ) from exc
        except tg_errors.FloodWaitError as exc:
            raise TelegramOperationError(
                f"FloodWait: wait {exc.seconds}s before sending.", code="FLOOD_WAIT", status_code=429
            ) from exc
        except Exception as exc:
            raise TelegramOperationError(f"Test publish failed: {type(exc).__name__}: {exc}") from exc

    async def fetch_missed_messages(
        self, identifier_or_peer: str | int, min_message_id: int, limit: int = 100
    ) -> list[IncomingTelegramEvent]:
        client = self._require_client()
        ref = _normalize_target_identifier(identifier_or_peer)
        entity = await client.get_entity(ref)
        recovered: list[IncomingTelegramEvent] = []
        async for msg in client.iter_messages(entity, min_id=min_message_id, reverse=True, limit=limit):
            if isinstance(msg, tl_types.Message):
                recovered.append(extract_incoming_event_from_telethon_message(msg, chat=entity))
        return recovered

    async def publish_job_payload(
        self,
        *,
        target_identifier: str | int,
        source_identifier: str | int,
        content_type: str,
        text: str,
        entities_json: str,
        source_message_ids: list[int],
        media_descriptors: list[dict[str, Any]],
    ) -> list[int]:
        if not self._client or not self._client.is_connected():
            raise TransientPublishError("Telegram client disconnected prior to send", code="CLIENT_DISCONNECTED")

        client = self._client
        target_ref = _normalize_target_identifier(target_identifier)
        source_ref = _normalize_target_identifier(source_identifier)
        tl_entities = deserialize_entities(entities_json)

        # Prepare media references BEFORE dispatching network send to target (so pre-send errors are safe to retry)
        files_to_send: list[Any] = []
        voice_note = content_type == "voice"

        if content_type != "text":
            cache_root = Path(get_settings().MEDIA_CACHE_DIR)
            cache_root.mkdir(parents=True, exist_ok=True)

            # Check if local cache paths already exist; otherwise pull from source messages
            missing_ids: list[int] = []
            local_by_msg_id: dict[int, str] = {}
            for desc in media_descriptors:
                mid = int(desc["telegram_message_id"])
                cpath = desc.get("local_cache_path")
                if cpath and Path(cpath).exists():
                    local_by_msg_id[mid] = cpath
                else:
                    missing_ids.append(mid)

            source_msgs_by_id: dict[int, Any] = {}
            if missing_ids:
                try:
                    fetched = await client.get_messages(source_ref, ids=missing_ids)
                    if not isinstance(fetched, list):
                        fetched = [fetched]
                    for m in fetched:
                        if m is not None:
                            if getattr(m, "noforwards", False):
                                raise PermanentPublishError(
                                    "Source message has content protection (noforwards) enabled.",
                                    code="PROTECTED_CONTENT",
                                )
                            source_msgs_by_id[int(m.id)] = m
                except PermanentPublishError:
                    raise
                except tg_errors.FloodWaitError as exc:
                    raise TransientPublishError(
                        f"FloodWait fetching source media ({exc.seconds}s)",
                        retry_after_seconds=int(exc.seconds),
                        code="FLOOD_WAIT",
                    ) from exc
                except Exception as exc:
                    raise TransientPublishError(
                        f"Failed to fetch source media prior to publish: {type(exc).__name__}",
                        code="SOURCE_FETCH_ERROR",
                    ) from exc

            for desc in media_descriptors:
                mid = int(desc["telegram_message_id"])
                if mid in local_by_msg_id:
                    files_to_send.append(local_by_msg_id[mid])
                elif mid in source_msgs_by_id and getattr(source_msgs_by_id[mid], "media", None):
                    src_msg = source_msgs_by_id[mid]
                    fname = safe_filename(desc.get("file_name"), fallback=f"msg_{mid}.bin")
                    dest_file = cache_root / f"src_{abs(hash(str(source_ref)))}_{mid}_{fname}"
                    if not dest_file.exists():
                        downloaded = await client.download_media(src_msg, file=str(dest_file))
                        if not downloaded:
                            raise PermanentPublishError(
                                f"Source media #{mid} is unavailable or protected.",
                                code="MEDIA_UNAVAILABLE",
                            )
                        files_to_send.append(str(downloaded))
                    else:
                        files_to_send.append(str(dest_file))

            if not files_to_send:
                raise PermanentPublishError(
                    "No valid media items available to publish for this event.",
                    code="EMPTY_MEDIA",
                )

        # === CRITICAL SECTION: Dispatching publish call to Target on Telegram ===
        try:
            if content_type == "text":
                sent = await client.send_message(
                    target_ref,
                    text or "",
                    formatting_entities=tl_entities or None,
                    link_preview=True,
                )
                return [int(sent.id)]

            if content_type == "album" or len(files_to_send) > 1:
                sent_list = await client.send_file(
                    target_ref,
                    file=files_to_send,
                    caption=text or None,
                    formatting_entities=tl_entities or None,
                )
                if isinstance(sent_list, list):
                    return [int(m.id) for m in sent_list]
                return [int(sent_list.id)]

            sent_single = await client.send_file(
                target_ref,
                file=files_to_send[0],
                caption=text or None,
                formatting_entities=tl_entities or None,
                voice_note=voice_note,
            )
            return [int(sent_single.id)]

        except tg_errors.FloodWaitError as exc:
            # Explicit server-side rejection BEFORE accepting message -> safe RETRY_WAIT
            raise TransientPublishError(
                f"Telegram FloodWait: retry after {exc.seconds}s",
                retry_after_seconds=int(exc.seconds) + 2,
                code="FLOOD_WAIT",
            ) from exc
        except (
            tg_errors.ChatWriteForbiddenError,
            tg_errors.ChatAdminRequiredError,
            tg_errors.UserBannedInChannelError,
            tg_errors.ChannelPrivateError,
            tg_errors.ChatSendMediaForbiddenError,
            tg_errors.ChatForwardsRestrictedError,
        ) as exc:
            # Explicit server-side permanent rejection -> FAILED
            raise PermanentPublishError(
                f"Target rejected publish ({type(exc).__name__}): {exc}",
                code=type(exc).__name__.upper(),
            ) from exc
        except (TimeoutError, ConnectionError, OSError, tg_errors.TimedOutError) as exc:
            # Network or RPC timeout AFTER request left client -> delivery is UNCERTAIN -> UNKNOWN!
            raise AmbiguousPublishError(
                f"Ambiguous outcome during Telegram send ({type(exc).__name__}): {exc}"
            ) from exc
        except Exception as exc:
            raise PermanentPublishError(f"Telegram publish error ({type(exc).__name__}): {exc}") from exc

    async def fetch_recent_target_posts(
        self, target_identifier: str | int, limit: int = 20
    ) -> list[TargetRecentPost]:
        client = self._require_client()
        ref = _normalize_target_identifier(target_identifier)
        msgs = await client.get_messages(ref, limit=limit)
        posts: list[TargetRecentPost] = []
        grouped_counts: dict[int, int] = {}
        for m in msgs:
            if getattr(m, "grouped_id", None):
                gid = int(m.grouped_id)
                grouped_counts[gid] = grouped_counts.get(gid, 0) + 1
        for m in msgs:
            if not isinstance(m, tl_types.Message):
                continue
            gid = getattr(m, "grouped_id", None)
            posts.append(
                TargetRecentPost(
                    message_id=int(m.id),
                    text=(getattr(m, "message", None) or "").strip(),
                    published_at=getattr(m, "date", None) or utcnow(),
                    has_media=bool(getattr(m, "media", None)),
                    media_count=grouped_counts.get(int(gid), 1) if gid else 1,
                )
            )
        return posts


# Singleton gateway instance (can be swapped via set_telegram_gateway in tests)
_gateway_instance: TelegramGatewayProtocol = TelethonClientManager()


def get_telegram_gateway() -> TelegramGatewayProtocol:
    return _gateway_instance


def set_telegram_gateway(gateway: TelegramGatewayProtocol) -> None:
    global _gateway_instance
    _gateway_instance = gateway
