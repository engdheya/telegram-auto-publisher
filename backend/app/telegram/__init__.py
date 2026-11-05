"""Telegram package exports."""

from app.telegram.formatter import (
    deserialize_entities,
    serialize_entities,
    transform_text_and_entities,
    utf16_len,
)
from app.telegram.gateway import (
    IncomingMediaItem,
    IncomingTelegramEvent,
    TargetRecentPost,
    TelegramGatewayProtocol,
    TelethonClientManager,
    get_telegram_gateway,
    set_telegram_gateway,
)

__all__ = [
    "IncomingMediaItem",
    "IncomingTelegramEvent",
    "TargetRecentPost",
    "TelegramGatewayProtocol",
    "TelethonClientManager",
    "get_telegram_gateway",
    "set_telegram_gateway",
    "serialize_entities",
    "deserialize_entities",
    "transform_text_and_entities",
    "utf16_len",
]
