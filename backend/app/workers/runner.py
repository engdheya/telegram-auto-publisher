"""Coordinated persistent Background Worker: Telethon Listener + Album Aggregator + Queue Publisher + Watchdog."""

import asyncio
import os
import signal
import time
from pathlib import Path

from app.core.config import get_settings
from app.core.logging import logger
from app.database import session as db_session
from app.database.init_db import init_database
from app.repositories.audit_repo import AuditRepository
from app.repositories.job_repo import JobRepository
from app.repositories.setting_repo import SettingRepository
from app.services.ingestion_service import IngestionService
from app.services.publishing_engine import PublishingEngine
from app.services.telegram_service import TelegramAccountService
from app.telegram.gateway import TelethonClientManager, get_telegram_gateway
from app.telegram.listener import TelethonChannelListener
from app.utils.time import utcnow


class WorkerOrchestrator:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.worker_id = self.settings.WORKER_ID
        self._stop_event = asyncio.Event()
        self._listener = TelethonChannelListener()

    def request_stop(self) -> None:
        self._stop_event.set()

    def _record_heartbeat(self) -> None:
        with db_session.SessionLocal() as db:
            SettingRepository.set_value(
                db,
                "runtime.worker_heartbeat",
                {"worker_id": self.worker_id, "timestamp": utcnow().isoformat(), "pid": os.getpid()},
                category="runtime",
                description="Background worker liveness heartbeat",
                updated_by=self.worker_id,
            )
            db.commit()

    def _cleanup_expired_media_cache(self) -> None:
        with db_session.SessionLocal() as db:
            retention_hours = float(
                SettingRepository.get_value(
                    db, "storage.media_retention_hours", self.settings.MEDIA_CACHE_RETENTION_HOURS
                )
            )
        cache_dir = Path(self.settings.MEDIA_CACHE_DIR)
        if not cache_dir.exists():
            return
        cutoff = time.time() - (retention_hours * 3600.0)
        for item in cache_dir.iterdir():
            if item.is_file() and item.stat().st_mtime < cutoff:
                try:
                    item.unlink()
                except OSError:
                    pass

    async def _ensure_telegram_connected(self) -> None:
        gateway = get_telegram_gateway()
        with db_session.SessionLocal() as db:
            acc = TelegramAccountService.get_or_create_account(db)
            should_connect = bool(
                acc.encrypted_session and acc.api_id and acc.api_hash_encrypted and acc.auto_reconnect
            )
            if not should_connect:
                return

            if gateway.is_live_connected():
                acc.is_connected = True
                acc.heartbeat_at = utcnow()
                db.commit()
                if isinstance(gateway, TelethonClientManager) and gateway.get_raw_client():
                    self._listener.attach(gateway.get_raw_client())
                return

            try:
                await TelegramAccountService.reconnect_saved_session(db, gateway, actor_username=self.worker_id)
                if isinstance(gateway, TelethonClientManager) and gateway.get_raw_client():
                    self._listener.attach(gateway.get_raw_client())
                await IngestionService.catch_up_missed_messages(db, gateway)
            except Exception as exc:
                logger.warning("Auto-reconnect attempt deferred: %s", exc)

    async def startup_recovery(self) -> None:
        init_database()
        with db_session.SessionLocal() as db:
            stale = JobRepository.recover_stale_processing_jobs(
                db, stale_timeout_seconds=0  # Any in-flight PROCESSING job from previous dead worker -> UNKNOWN
            )
            if stale:
                AuditRepository.record(
                    db,
                    level="WARNING",
                    category="QUEUE",
                    action="STARTUP_STALE_JOBS_RECOVERED",
                    actor_username=self.worker_id,
                    message=f"Transitioned {len(stale)} interrupted PROCESSING job(s) to UNKNOWN on worker startup.",
                    commit=True,
                )
            AuditRepository.record(
                db,
                level="INFO",
                category="SYSTEM",
                action="WORKER_STARTED",
                actor_username=self.worker_id,
                message=f"Background worker '{self.worker_id}' started (PID={os.getpid()}).",
                commit=True,
            )
        self._record_heartbeat()
        await self._ensure_telegram_connected()

    async def album_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                with db_session.SessionLocal() as db:
                    IngestionService.finalize_ready_albums(db)
            except Exception as exc:
                logger.error("Album aggregation loop error: %s", exc)
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=0.5)
            except TimeoutError:
                pass

    async def publisher_loop(self) -> None:
        poll = max(0.3, float(self.settings.WORKER_POLL_INTERVAL_SECONDS))
        while not self._stop_event.is_set():
            processed = False
            try:
                gateway = get_telegram_gateway()
                if gateway.is_live_connected():
                    with db_session.SessionLocal() as db:
                        job = await PublishingEngine.process_next_job(
                            db, gateway=gateway, worker_id=self.worker_id
                        )
                        processed = job is not None
            except Exception as exc:
                logger.error("Publisher queue loop error: %s", exc)

            if not processed:
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=poll)
                except TimeoutError:
                    pass

    async def watchdog_loop(self) -> None:
        ticks = 0
        while not self._stop_event.is_set():
            try:
                self._record_heartbeat()
                await self._ensure_telegram_connected()
                ticks += 1
                if ticks % 12 == 0:
                    with db_session.SessionLocal() as db:
                        JobRepository.recover_stale_processing_jobs(
                            db, stale_timeout_seconds=self.settings.WORKER_STALE_LOCK_TIMEOUT_SECONDS
                        )
                    self._cleanup_expired_media_cache()
            except Exception as exc:
                logger.error("Watchdog loop error: %s", exc)

            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=5.0)
            except TimeoutError:
                pass

    async def run(self) -> None:
        await self.startup_recovery()
        tasks = [
            asyncio.create_task(self.album_loop(), name="album-flusher"),
            asyncio.create_task(self.publisher_loop(), name="queue-publisher"),
            asyncio.create_task(self.watchdog_loop(), name="watchdog"),
        ]
        await self._stop_event.wait()
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        logger.info("Worker '%s' stopped cleanly.", self.worker_id)


async def _main() -> None:
    orchestrator = WorkerOrchestrator()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, orchestrator.request_stop)
        except NotImplementedError:
            pass
    await orchestrator.run()


if __name__ == "__main__":
    asyncio.run(_main())
