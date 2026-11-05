"""Telegram account connection, OTP login, 2FA, reconnect, and logout endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin
from app.database.session import get_db
from app.models import User
from app.schemas.telegram import (
    TelegramAccountStatusResponse,
    TelegramAutoReconnectUpdate,
    TelegramCredentialsRequest,
    TelegramPasswordRequest,
    TelegramVerifyCodeRequest,
)
from app.services.ingestion_service import IngestionService
from app.services.telegram_service import TelegramAccountService
from app.telegram.gateway import get_telegram_gateway

router = APIRouter(prefix="/telegram", tags=["Telegram Account"])


@router.get("/status", response_model=TelegramAccountStatusResponse)
def get_telegram_status(
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TelegramAccountStatusResponse:
    gateway = get_telegram_gateway()
    acc = TelegramAccountService.get_or_create_account(db)
    return TelegramAccountService.to_status_response(acc, gateway)


@router.post("/send-code", response_model=TelegramAccountStatusResponse)
async def send_login_code(
    payload: TelegramCredentialsRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> TelegramAccountStatusResponse:
    gateway = get_telegram_gateway()
    return await TelegramAccountService.request_login_code(db, payload, gateway, admin.username)


@router.post("/verify-code", response_model=TelegramAccountStatusResponse)
async def verify_login_code(
    payload: TelegramVerifyCodeRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> TelegramAccountStatusResponse:
    gateway = get_telegram_gateway()
    return await TelegramAccountService.verify_code(db, payload, gateway, admin.username)


@router.post("/verify-password", response_model=TelegramAccountStatusResponse)
async def verify_2fa_password(
    payload: TelegramPasswordRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> TelegramAccountStatusResponse:
    gateway = get_telegram_gateway()
    return await TelegramAccountService.verify_2fa_password(db, payload, gateway, admin.username)


@router.post("/reconnect", response_model=TelegramAccountStatusResponse)
async def reconnect_telegram(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> TelegramAccountStatusResponse:
    gateway = get_telegram_gateway()
    resp = await TelegramAccountService.reconnect_saved_session(db, gateway, admin.username)
    await IngestionService.catch_up_missed_messages(db, gateway)
    return resp


@router.patch("/auto-reconnect", response_model=TelegramAccountStatusResponse)
def set_auto_reconnect(
    payload: TelegramAutoReconnectUpdate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> TelegramAccountStatusResponse:
    gateway = get_telegram_gateway()
    acc = TelegramAccountService.get_or_create_account(db)
    acc.auto_reconnect = payload.auto_reconnect
    db.commit()
    db.refresh(acc)
    return TelegramAccountService.to_status_response(acc, gateway)


@router.post("/logout", response_model=TelegramAccountStatusResponse)
async def logout_telegram(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> TelegramAccountStatusResponse:
    gateway = get_telegram_gateway()
    return await TelegramAccountService.logout_and_unlink(db, gateway, admin.username)
