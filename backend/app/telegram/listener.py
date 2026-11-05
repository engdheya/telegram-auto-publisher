"""Live Telethon NewMessage listener subscribing strictly to new posts (ignoring edits & deletes)."""

from telethon import TelegramClient, events

from app.core.logging import logger
from app.database.session import SessionLocal
from app.services.ingestion_service import IngestionService
from app.telegram.gateway import extract_incoming_event_from_telethon_message


class TelethonChannelListener:
    """Attaches NewMessage event handler to an authorized Telethon client."""

    def __init__(self) -> None:
        self._attached_client: TelegramClient | None = None

    def attach(self, client: TelegramClient) -> None:
        if self._attached_client is client:
            return
        client.add_event_handler(self._on_new_message, events.NewMessage(incoming=True, outgoing=True))
        self._attached_client = client
        logger.info("Attached Telethon NewMessage listener (edits and deletions are intentionally ignored).")

    async def _on_new_message(self, event: events.NewMessage.Event) -> None:
        try:
            msg = event.message
            # Rule 4: Do NOT republish edited messages
            if getattr(msg, "edit_date", None) is not None:
                return
            chat = await event.get_chat()
            normalized = extract_incoming_event_from_telethon_message(msg, chat=chat)
            with SessionLocal() as db:
                IngestionService.ingest_event(db, normalized)
        except Exception as exc:
            logger.error("Error processing live NewMessage event: %s", type(exc).__name__)
