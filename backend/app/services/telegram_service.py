"""Encrypted Telegram account management service (login, 2FA, session storage, reconnect, logout)."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.crypto import SecretBox
from app.core.exceptions import AppError, TelegramOperationError
from app.models import TelegramAccount
from app.repositories.audit_repo import AuditRepository
from app.schemas.telegram import (
    TelegramAccountStatusResponse,
    TelegramCredentialsRequest,
    TelegramPasswordRequest,
    TelegramVerifyCodeRequest,
)
from app.telegram.gateway import TelegramGatewayProtocol
from app.utils.sanitize import mask_phone
from app.utils.time import utcnow


class TelegramAccountService:
    @staticmethod
    def get_or_create_account(db: Session) -> TelegramAccount:
        acc = db.execute(select(TelegramAccount).order_by(TelegramAccount.id.asc()).limit(1)).scalar_one_or_none()
        if acc is None:
            acc = TelegramAccount(
                label="Primary Telegram Account",
                auth_state="UNCONFIGURED",
                is_connected=False,
                auto_reconnect=True,
            )
            db.add(acc)
            db.commit()
            db.refresh(acc)
        return acc

    @staticmethod
    def to_status_response(
        acc: TelegramAccount, gateway: TelegramGatewayProtocol
    ) -> TelegramAccountStatusResponse:
        return TelegramAccountStatusResponse(
            id=acc.id,
            label=acc.label,
            api_id=acc.api_id,
            has_api_hash=bool(acc.api_hash_encrypted),
            masked_phone=mask_phone(acc.phone_number),
            has_saved_session=bool(acc.encrypted_session),
            auth_state=acc.auth_state,
            telegram_user_id=acc.telegram_user_id,
            telegram_username=acc.telegram_username,
            telegram_display_name=acc.telegram_display_name,
            is_connected=acc.is_connected,
            live_transport_connected=gateway.is_live_connected(),
            auto_reconnect=acc.auto_reconnect,
            reconnect_attempts=acc.reconnect_attempts,
            last_connected_at=acc.last_connected_at,
            last_disconnected_at=acc.last_disconnected_at,
            heartbeat_at=acc.heartbeat_at,
            last_error=acc.last_error,
            updated_at=acc.updated_at,
        )

    @staticmethod
    async def request_login_code(
        db: Session,
        payload: TelegramCredentialsRequest,
        gateway: TelegramGatewayProtocol,
        actor_username: str,
    ) -> TelegramAccountStatusResponse:
        box = SecretBox()
        acc = TelegramAccountService.get_or_create_account(db)

        pending_session, phone_code_hash = await gateway.send_login_code(
            api_id=payload.api_id,
            api_hash=payload.api_hash.strip(),
            phone_number=payload.phone_number.strip(),
        )

        acc.label = payload.label
        acc.api_id = payload.api_id
        acc.api_hash_encrypted = box.encrypt(payload.api_hash.strip())
        acc.phone_number = payload.phone_number.strip()
        acc.pending_session_encrypted = box.encrypt(pending_session)
        acc.phone_code_hash_encrypted = box.encrypt(phone_code_hash)
        acc.auto_reconnect = payload.auto_reconnect
        acc.auth_state = "AWAITING_CODE"
        acc.is_connected = False
        acc.last_error = None

        AuditRepository.record(
            db,
            level="INFO",
            category="TELEGRAM",
            action="LOGIN_CODE_REQUESTED",
            actor_username=actor_username,
            entity_type="telegram_account",
            entity_id=acc.id,
            message=f"Requested Telegram verification code for {mask_phone(acc.phone_number)}.",
            details={"api_id": acc.api_id, "masked_phone": mask_phone(acc.phone_number)},
        )
        db.commit()
        db.refresh(acc)
        return TelegramAccountService.to_status_response(acc, gateway)

    @staticmethod
    async def verify_code(
        db: Session,
        payload: TelegramVerifyCodeRequest,
        gateway: TelegramGatewayProtocol,
        actor_username: str,
    ) -> TelegramAccountStatusResponse:
        box = SecretBox()
        acc = TelegramAccountService.get_or_create_account(db)
        if not acc.api_id or not acc.api_hash_encrypted or not acc.pending_session_encrypted or not acc.phone_code_hash_encrypted:
            raise AppError("No pending Telegram login flow found. Submit API ID, API Hash, and Phone first.")

        api_hash = box.decrypt(acc.api_hash_encrypted) or ""
        pending_session = box.decrypt(acc.pending_session_encrypted) or ""
        phone_code_hash = box.decrypt(acc.phone_code_hash_encrypted) or ""

        try:
            result = await gateway.verify_code(
                api_id=acc.api_id,
                api_hash=api_hash,
                pending_session=pending_session,
                phone_number=acc.phone_number or "",
                code=payload.code,
                phone_code_hash=phone_code_hash,
                password=payload.password,
            )
        except TelegramOperationError as exc:
            acc.last_error = exc.message
            db.commit()
            raise

        if result.get("state") == "AWAITING_PASSWORD":
            acc.auth_state = "AWAITING_PASSWORD"
            acc.pending_session_encrypted = box.encrypt(result["pending_session"])
            acc.last_error = None
            AuditRepository.record(
                db,
                level="INFO",
                category="TELEGRAM",
                action="LOGIN_2FA_REQUIRED",
                actor_username=actor_username,
                entity_type="telegram_account",
                entity_id=acc.id,
                message="Telegram account requires 2FA Cloud Password to complete sign-in.",
            )
            db.commit()
            db.refresh(acc)
            return TelegramAccountService.to_status_response(acc, gateway)

        now = utcnow()
        acc.encrypted_session = box.encrypt(result["session_str"])
        acc.pending_session_encrypted = None
        acc.phone_code_hash_encrypted = None
        acc.auth_state = "CONNECTED"
        acc.is_connected = True
        acc.reconnect_attempts = 0
        acc.telegram_user_id = result.get("telegram_user_id")
        acc.telegram_username = result.get("telegram_username")
        acc.telegram_display_name = result.get("telegram_display_name")
        acc.last_connected_at = now
        acc.heartbeat_at = now
        acc.last_error = None

        AuditRepository.record(
            db,
            level="INFO",
            category="TELEGRAM",
            action="ACCOUNT_CONNECTED",
            actor_username=actor_username,
            entity_type="telegram_account",
            entity_id=acc.id,
            message=f"Telegram account '{acc.telegram_display_name}' connected with encrypted session.",
        )
        db.commit()
        db.refresh(acc)
        return TelegramAccountService.to_status_response(acc, gateway)

    @staticmethod
    async def verify_2fa_password(
        db: Session,
        payload: TelegramPasswordRequest,
        gateway: TelegramGatewayProtocol,
        actor_username: str,
    ) -> TelegramAccountStatusResponse:
        box = SecretBox()
        acc = TelegramAccountService.get_or_create_account(db)
        if acc.auth_state != "AWAITING_PASSWORD" or not acc.pending_session_encrypted or not acc.api_id:
            raise AppError("Account is not awaiting 2FA password.")

        api_hash = box.decrypt(acc.api_hash_encrypted) or ""
        pending_session = box.decrypt(acc.pending_session_encrypted) or ""

        result = await gateway.verify_2fa_password(
            api_id=acc.api_id,
            api_hash=api_hash,
            pending_session=pending_session,
            password=payload.password,
        )

        now = utcnow()
        acc.encrypted_session = box.encrypt(result["session_str"])
        acc.pending_session_encrypted = None
        acc.phone_code_hash_encrypted = None
        acc.auth_state = "CONNECTED"
        acc.is_connected = True
        acc.reconnect_attempts = 0
        acc.telegram_user_id = result.get("telegram_user_id")
        acc.telegram_username = result.get("telegram_username")
        acc.telegram_display_name = result.get("telegram_display_name")
        acc.last_connected_at = now
        acc.heartbeat_at = now
        acc.last_error = None

        AuditRepository.record(
            db,
            level="INFO",
            category="TELEGRAM",
            action="ACCOUNT_2FA_CONNECTED",
            actor_username=actor_username,
            entity_type="telegram_account",
            entity_id=acc.id,
            message=f"Telegram account '{acc.telegram_display_name}' authenticated via 2FA.",
        )
        db.commit()
        db.refresh(acc)
        return TelegramAccountService.to_status_response(acc, gateway)

    @staticmethod
    async def reconnect_saved_session(
        db: Session, gateway: TelegramGatewayProtocol, actor_username: str = "system"
    ) -> TelegramAccountStatusResponse:
        box = SecretBox()
        acc = TelegramAccountService.get_or_create_account(db)
        if not acc.encrypted_session or not acc.api_id or not acc.api_hash_encrypted:
            raise AppError("No saved encrypted Telegram session available to reconnect.")

        api_hash = box.decrypt(acc.api_hash_encrypted) or ""
        session_str = box.decrypt(acc.encrypted_session) or ""

        try:
            info = await gateway.connect_saved_session(acc.api_id, api_hash, session_str)
            now = utcnow()
            acc.auth_state = "CONNECTED"
            acc.is_connected = True
            acc.reconnect_attempts = 0
            acc.telegram_user_id = info.get("telegram_user_id", acc.telegram_user_id)
            acc.telegram_username = info.get("telegram_username", acc.telegram_username)
            acc.telegram_display_name = info.get("telegram_display_name", acc.telegram_display_name)
            acc.last_connected_at = now
            acc.heartbeat_at = now
            acc.last_error = None

            AuditRepository.record(
                db,
                level="INFO",
                category="TELEGRAM",
                action="SESSION_RECONNECTED",
                actor_username=actor_username,
                entity_type="telegram_account",
                entity_id=acc.id,
                message=f"Reconnected Telegram session for '{acc.telegram_display_name}'.",
            )
            db.commit()
            db.refresh(acc)
            return TelegramAccountService.to_status_response(acc, gateway)
        except Exception as exc:
            now = utcnow()
            acc.is_connected = False
            acc.reconnect_attempts = (acc.reconnect_attempts or 0) + 1
            acc.last_disconnected_at = now
            acc.last_error = str(exc)
            if isinstance(exc, TelegramOperationError) and exc.code == "SESSION_REVOKED":
                acc.auth_state = "AUTH_ERROR"
            AuditRepository.record(
                db,
                level="ERROR",
                category="TELEGRAM",
                action="SESSION_RECONNECT_FAILED",
                actor_username=actor_username,
                entity_type="telegram_account",
                entity_id=acc.id,
                message=f"Telegram reconnect attempt #{acc.reconnect_attempts} failed: {exc}",
            )
            db.commit()
            raise

    @staticmethod
    async def logout_and_unlink(
        db: Session, gateway: TelegramGatewayProtocol, actor_username: str
    ) -> TelegramAccountStatusResponse:
        box = SecretBox()
        acc = TelegramAccountService.get_or_create_account(db)
        api_hash = box.decrypt(acc.api_hash_encrypted) if acc.api_hash_encrypted else None
        session_str = box.decrypt(acc.encrypted_session) if acc.encrypted_session else None

        await gateway.disconnect_and_logout(acc.api_id, api_hash, session_str, revoke=True)

        now = utcnow()
        acc.encrypted_session = None
        acc.pending_session_encrypted = None
        acc.phone_code_hash_encrypted = None
        acc.auth_state = "DISCONNECTED" if acc.api_id else "UNCONFIGURED"
        acc.is_connected = False
        acc.telegram_user_id = None
        acc.telegram_username = None
        acc.telegram_display_name = None
        acc.last_disconnected_at = now
        acc.last_error = None

        AuditRepository.record(
            db,
            level="INFO",
            category="TELEGRAM",
            action="ACCOUNT_LOGGED_OUT",
            actor_username=actor_username,
            entity_type="telegram_account",
            entity_id=acc.id,
            message="Logged out from Telegram and wiped encrypted session from database.",
        )
        db.commit()
        db.refresh(acc)
        return TelegramAccountService.to_status_response(acc, gateway)
