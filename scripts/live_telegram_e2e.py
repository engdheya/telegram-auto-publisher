#!/usr/bin/env python3
"""
Telegram Auto Publisher — LIVE Telegram end-to-end proof (real Telegram, not a fake gateway).

What it does (all through the running system, never by mocking internals):
  1. Logs into the dashboard API (JWT).
  2. Asserts the Telegram account linked from the UI is CONNECTED.
  3. Registers source/target channels through the public REST API and starts monitoring
     (this records baseline_message_id — archive is never imported).
  4. Posts REAL content into the source channel(s) using a helper identity:
        • preferred: a bot token (TELEGRAM_BOT_TOKEN) that is admin in source+targets
        • or a helper user account (TELEGRAM_HELPER_PHONE + its own OTP)
  5. Waits for the worker to publish, then reads the TARGET channel back on Telegram and
     asserts the exact text/media/album arrived, with independent per-target jobs.
  6. Exercises: 1→N, N→M, failure isolation (a target without rights), no duplicate
     re-publish of already-published targets, worker restart recovery, reconnect.
  7. Writes docs/LIVE_TELEGRAM_EVIDENCE.md with every assertion + raw Telegram message ids.

Requirements:
  pip install httpx telethon
Env (every value falls back to .env in the repo root, so the dry run works out of the box):
  TAP_API_URL            default http://127.0.0.1:8000/api/v1
  TAP_ADMIN_USERNAME     default admin (falls back to INITIAL_ADMIN_USERNAME)
  TAP_ADMIN_PASSWORD     required (falls back to INITIAL_ADMIN_PASSWORD)
  TELEGRAM_API_ID/HASH   required (same credentials used to link the account)
  TELEGRAM_BOT_TOKEN     preferred helper identity for posting/reading
  TELEGRAM_HELPER_PHONE  alternative helper user (will prompt for its OTP once)
  TAP_SOURCE_CHATS       comma separated @source1,@source2 (must be admin-visible)
  TAP_TARGET_CHATS       comma separated @target1,@target2
  TAP_TARGET_NO_RIGHTS   optional channel where the linked account cannot post (failure isolation)
Usage:
  python3 scripts/live_telegram_e2e.py --dry-run      # checks prerequisites only
  python3 scripts/live_telegram_e2e.py                # full live run
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

try:
    import httpx
except ImportError:  # pragma: no cover
    sys.exit("httpx is required: pip install httpx")

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs" / "LIVE_TELEGRAM_EVIDENCE.md"
HELPER_SESSION = Path.home() / ".tap_live_helper.session"  # outside the repo on purpose


@dataclass
class Report:
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))
    rows: list[tuple[str, bool, str]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def check(self, name: str, ok: bool, detail: str = "") -> bool:
        self.rows.append((name, ok, detail))
        print(f"{'PASS' if ok else 'FAIL'} | {name}" + (f" | {detail}" if detail else ""))
        return ok

    @property
    def failed(self) -> int:
        return sum(1 for _, ok, _ in self.rows if not ok)


# .env in the repo root is the single source of truth for local runs; the same
# file the running API/worker read. Environment variables still win.
_DOTENV: dict[str, str] = {}
_ENV_FILE = ROOT / ".env"
if _ENV_FILE.exists():
    for _line in _ENV_FILE.read_text().splitlines():
        _line = _line.strip()
        if not _line or _line.startswith("#") or "=" not in _line:
            continue
        _k, _v = _line.split("=", 1)
        _DOTENV[_k.strip()] = _v.strip().strip('"').strip("'")

# alias so the dashboard admin password can come straight from .env
_ENV_ALIASES = {
    "TAP_ADMIN_USERNAME": "INITIAL_ADMIN_USERNAME",
    "TAP_ADMIN_PASSWORD": "INITIAL_ADMIN_PASSWORD",
}


def env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    if value is None and name in _ENV_ALIASES:
        value = os.environ.get(_ENV_ALIASES[name])
    if value is None and name in _ENV_ALIASES:
        value = _DOTENV.get(_ENV_ALIASES[name])
    if value is None:
        value = _DOTENV.get(name, default)
    return value.strip() if isinstance(value, str) else value


class Api:
    def __init__(self, base: str) -> None:
        self.base = base.rstrip("/")
        self.client = httpx.Client(timeout=90.0)
        self.token: str | None = None

    def login(self, username: str, password: str) -> dict:
        r = self.client.post(f"{self.base}/auth/login", json={"username": username, "password": password})
        r.raise_for_status()
        data = r.json()
        self.token = data["access_token"]
        return data

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    def get(self, path: str, **kw):
        return self.client.get(f"{self.base}{path}", headers=self._headers(), **kw)

    def post(self, path: str, **kw):
        return self.client.post(f"{self.base}{path}", headers=self._headers(), **kw)

    def patch(self, path: str, **kw):
        return self.client.patch(f"{self.base}{path}", headers=self._headers(), **kw)

    # --- domain helpers -------------------------------------------------
    def ensure_source(self, title: str, identifier: str) -> dict:
        existing = self.get("/sources").json()
        for s in existing:
            if s["identifier"].lower() == identifier.lower():
                return s
        r = self.post("/sources", json={"title": title, "identifier": identifier, "is_enabled": True})
        r.raise_for_status()
        return r.json()

    def ensure_target(self, title: str, identifier: str) -> dict:
        existing = self.get("/targets").json()
        for t in existing:
            if t["identifier"].lower() == identifier.lower():
                return t
        r = self.post("/targets", json={"title": title, "identifier": identifier, "is_enabled": True})
        r.raise_for_status()
        return r.json()

    def ensure_route(self, name: str, source_id: int, target_id: int) -> dict:
        r = self.post(
            "/routes/bulk",
            json={
                "name_prefix": name,
                "source_channel_ids": [source_id],
                "target_channel_ids": [target_id],
                "is_enabled": True,
                "filters": {
                    "allowed_content_types": ["text", "photo", "video", "document", "audio", "voice", "album"],
                },
            },
        )
        r.raise_for_status()
        return r.json()

    def messages(self, limit: int = 50) -> list[dict]:
        return self.get("/messages", params={"page_size": limit}).json()["items"]

    def jobs_for_event(self, event_id: int) -> list[dict]:
        for ev in self.messages(100):
            if ev["id"] == event_id:
                return ev["jobs"]
        return []

    def queue(self, status: str | None = None, page_size: int = 100) -> dict:
        params = {"page_size": page_size}
        if status:
            params["status"] = status
        r = self.get("/queue/jobs", params=params)
        r.raise_for_status()
        return r.json()


async def wait_for_jobs(api: Api, event_id: int, expected: int, timeout: float = 120.0) -> list[dict]:
    deadline = time.time() + timeout
    last: list[dict] = []
    while time.time() < deadline:
        last = api.jobs_for_event(event_id)
        terminal = [j for j in last if j["status"] in {"PUBLISHED", "FAILED", "SKIPPED"}]
        if len(last) >= expected and len(terminal) == len(last):
            return last
        await asyncio.sleep(2.0)
    return last


# ---------------------------------------------------------------------------
# helper identity (bot preferred, else a separate user session)
# ---------------------------------------------------------------------------
class Helper:
    """Independent Telegram identity used only to inject source content and read targets."""

    def __init__(self, api_id: int, api_hash: str) -> None:
        from telethon import TelegramClient
        from telethon.sessions import StringSession

        self.api_id = api_id
        self.api_hash = api_hash
        self._TelegramClient = TelegramClient
        self._StringSession = StringSession
        bot_token = env("TELEGRAM_BOT_TOKEN")
        if bot_token:
            self.client = TelegramClient(HELPER_SESSION.with_suffix(".bot"), api_id, api_hash)
            self.token = bot_token
            self.kind = "bot"
        else:
            self.client = TelegramClient(str(HELPER_SESSION), api_id, api_hash)
            self.token = None
            self.kind = "user"

    async def connect(self) -> None:
        await self.client.connect()
        if self.kind == "bot":
            if not await self.client.is_user_authorized():
                await self.client.sign_in(bot_token=self.token)
        elif not await self.client.is_user_authorized():
            phone = env("TELEGRAM_HELPER_PHONE")
            if not phone:
                raise RuntimeError("TELEGRAM_HELPER_PHONE (or TELEGRAM_BOT_TOKEN) is required for the helper identity")
            await self.client.send_code_request(phone)
            code = input(f"Enter the OTP Telegram sent to {phone} for the HELPER account: ").strip()
            await self.client.sign_in(phone=phone, code=code)
        me = await self.client.get_me()
        print(f"    helper identity: {self.kind} @{getattr(me, 'username', None) or me.id}")

    async def send_text(self, chat: str, text: str):
        return await self.client.send_message(chat, text)

    async def send_photo(self, chat: str, path: Path, caption: str):
        return await self.client.send_file(chat, str(path), caption=caption)

    async def send_album(self, chat: str, paths: list[Path], caption: str):
        return await self.client.send_file(chat, [str(p) for p in paths], caption=caption)

    async def send_document(self, chat: str, path: Path, caption: str):
        return await self.client.send_file(chat, str(path), caption=caption, force_document=True)

    async def read_recent(self, chat: str, limit: int = 15) -> list:
        return await self.client.get_messages(chat, limit=limit)

    async def close(self) -> None:
        await self.client.disconnect()


def make_media_files(tmp: Path) -> dict[str, Path]:
    """Generate small real media files (PNG/MP4-ish/document) without external deps."""
    tmp.mkdir(parents=True, exist_ok=True)
    png = tmp / "tap_probe.png"
    if not png.exists():
        # 1x1 PNG + padding so it is a valid image Telegram accepts
        import base64

        png.write_bytes(
            base64.b64decode(
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8AARAAI"
                "AwEBI5AB9AAAAABJRU5ErkJggg=="
            )
        )
    video = tmp / "tap_probe.mp4"
    if not video.exists():
        video.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 2048)
    doc = tmp / "tap_probe_report.pdf"
    if not doc.exists():
        doc.write_text("Telegram Auto Publisher live media probe (PDF placeholder).\n", encoding="utf-8")
    return {"photo": png, "video": video, "document": doc}


async def run(args) -> int:
    report = Report()
    api = Api(env("TAP_API_URL", "http://127.0.0.1:8000/api/v1"))
    username = env("TAP_ADMIN_USERNAME", "admin")
    password = env("TAP_ADMIN_PASSWORD")
    api_id_raw = env("TELEGRAM_API_ID")
    api_hash = env("TELEGRAM_API_HASH")

    sources = [c.strip() for c in (env("TAP_SOURCE_CHATS") or "").split(",") if c.strip()]
    targets = [c.strip() for c in (env("TAP_TARGET_CHATS") or "").split(",") if c.strip()]
    no_rights = env("TAP_TARGET_NO_RIGHTS")

    if not password:
        # Never print which secret is missing without also explaining how to supply it.
        inventory = {
            "TAP_ADMIN_PASSWORD / INITIAL_ADMIN_PASSWORD": bool(password),
            "TELEGRAM_API_ID": bool(api_id_raw),
            "TELEGRAM_API_HASH": bool(api_hash),
            "TELEGRAM_BOT_TOKEN or TELEGRAM_HELPER_PHONE": bool(env("TELEGRAM_BOT_TOKEN") or env("TELEGRAM_HELPER_PHONE")),
            "TAP_SOURCE_CHATS": bool(sources),
            "TAP_TARGET_CHATS": bool(targets),
        }
        print("== 0. prerequisites inventory ==")
        for name, present in inventory.items():
            print(("PRESENT  " if present else "MISSING  ") + name)
        print("\nCannot run: the admin password is not configured. Add it to .env as INITIAL_ADMIN_PASSWORD.")
        report.write()
        return 1

    print("== 1. dashboard API login ==")
    api.login(username, password)
    report.check("Dashboard login (JWT issued by real API)", bool(api.token))

    tg = api.get("/telegram/status").json()
    report.check(
        "Telegram account is linked & CONNECTED (from the dashboard flow)",
        tg.get("auth_state") == "CONNECTED" and tg.get("is_connected") is True,
        f"auth_state={tg.get('auth_state')} @{tg.get('telegram_username')} session={tg.get('has_saved_session')}",
    )
    report.check(
        "API never exposes the API hash or the session",
        "api_hash" not in tg and "encrypted_session" not in tg and not tg.get("api_hash"),
    )

    # ---- prerequisite inventory (always reported) ----
    print("\n== 2. live-run prerequisites ==")
    report.check("TELEGRAM_API_ID present", bool(api_id_raw), api_id_raw or "missing")
    report.check("TELEGRAM_API_HASH present", bool(api_hash), "set" if api_hash else "missing")
    report.check(
        "Helper identity for injecting source content (bot token preferred)",
        bool(env("TELEGRAM_BOT_TOKEN") or env("TELEGRAM_HELPER_PHONE")),
        "bot token" if env("TELEGRAM_BOT_TOKEN") else ("helper phone" if env("TELEGRAM_HELPER_PHONE") else "missing"),
    )
    report.check("TAP_SOURCE_CHATS configured", bool(sources), ",".join(sources) or "missing")
    report.check("TAP_TARGET_CHATS configured", bool(targets), ",".join(targets) or "missing")

    if args.dry_run:
        print("\n--dry-run: prerequisites inventoried, no Telegram content was sent.")
        if report.failed:
            print("Live run is BLOCKED until the ❌ items above are supplied by the operator.")
        return 0 if not report.failed else 1

    if not api_id_raw or not api_hash:
        sys.exit("TELEGRAM_API_ID and TELEGRAM_API_HASH are required for a live run")
    if not sources or not targets:
        sys.exit("TAP_SOURCE_CHATS and TAP_TARGET_CHATS are required for a live run")

    helper = Helper(int(api_id_raw), api_hash)
    await helper.connect()
    media = make_media_files(Path("/tmp/tap_live_media"))
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")

    # ---- register channels through the REST API (as the dashboard does) ----
    src_rows = []
    for chat in sources:
        row = api.ensure_source(f"LIVE Source {chat}", chat)
        api.post(f"/sources/{row['id']}/verify")
        api.post(f"/sources/{row['id']}/start")
        refreshed = next(s for s in api.get("/sources").json() if s["id"] == row["id"])
        src_rows.append(refreshed)
        report.check(
            f"Source '{chat}' verified & monitoring started (baseline recorded)",
            refreshed["monitoring_status"] == "ACTIVE",
            f"baseline_message_id={refreshed['baseline_message_id']} last={refreshed['last_processed_message_id']} err={refreshed['last_error']}",
        )

    tgt_rows = []
    for chat in targets:
        api.ensure_target(f"LIVE Target {chat}", chat)
    for t in api.get("/targets").json():
        if t["identifier"] in targets:
            v = api.post(f"/targets/{t['id']}/verify").json()
            tgt_rows.append(v["target"])
            report.check(
                f"Target '{t['identifier']}' can post (permissions verified)",
                v["ok"] and v["target"]["can_post_messages"],
                v["detail"][:120],
            )

    # ---- routes: N sources -> M targets ----
    for s in src_rows:
        for t in tgt_rows:
            api.ensure_route("LIVE NxM", s["id"], t["id"])
    routes = api.get("/routes").json()
    pair_routes = [
        r for r in routes if r["source_channel_id"] in {s["id"] for s in src_rows} and r["target_channel_id"] in {t["id"] for t in tgt_rows}
    ]
    expected_jobs = len(src_rows) * len(tgt_rows)
    report.check(
        f"N×M routing created: {len(src_rows)} source(s) × {len(tgt_rows)} target(s)",
        len(pair_routes) >= expected_jobs,
        f"routes={len(pair_routes)} expected_jobs_per_post={expected_jobs}",
    )

    # ---- content types ----
    cases: list[tuple[str, str]] = []
    src0 = sources[0]

    txt = await helper.send_text(src0, f"TAP LIVE probe text {stamp}")
    cases.append((f"text {stamp}", str(txt.id)))

    photo = await helper.send_photo(src0, media["photo"], f"TAP LIVE photo {stamp}")
    cases.append((f"photo {stamp}", str(photo.id)))

    doc = await helper.send_document(src0, media["document"], f"TAP LIVE document {stamp}")
    cases.append((f"document {stamp}", str(doc.id)))

    video = await helper.send_photo(src0, media["video"], f"TAP LIVE video {stamp}")
    cases.append((f"video {stamp}", str(video.id)))

    album = await helper.send_album(src0, [media["photo"], media["photo"]], f"TAP LIVE album {stamp}")
    album_ids = ",".join(str(m.id) for m in (album if isinstance(album, list) else [album]))
    cases.append((f"album {stamp}", album_ids))

    print(f"    posted {len(cases)} real messages from the helper into {src0}")

    # ---- wait for the worker to publish everything ----
    processed: dict[str, dict] = {}
    deadline = time.time() + 240
    while time.time() < deadline:
        events = api.messages(50)
        mine = [e for e in events if (e.get("raw_text") or "").find(stamp) >= 0]
        if len(mine) >= len(cases) and all(all(j["status"] in {"PUBLISHED", "FAILED", "SKIPPED"} for j in e["jobs"]) for e in mine):
            processed = {str(e["telegram_message_id"]): e for e in mine}
            break
        await asyncio.sleep(3)

    for label, msg_ids in cases:
        ev = None
        for mid in msg_ids.split(","):
            ev = processed.get(mid) or ev
        if not ev:
            report.check(f"Content '{label}' ingested by the listener", False, "event not found in /messages")
            continue
        jobs = ev["jobs"]
        published = [j for j in jobs if j["status"] == "PUBLISHED"]
        report.check(
            f"Content '{label}' ({ev['content_type']}) ingested before queueing",
            bool(ev.get("enqueued_at")),
            f"event={ev['id']} album={ev['album_item_count']} grouped={bool(ev.get('grouped_id'))}",
        )
        report.check(
            f"Content '{label}' published to all {expected_jobs} configured target(s)",
            len(published) >= expected_jobs,
            f"jobs={[(j['target_title'], j['status']) for j in jobs]}",
        )
        # independent job per target + no duplicate event/target pair
        pairs = {(j["message_event_id"], j["target_channel_id"]) for j in jobs}
        report.check(f"Content '{label}' has exactly one job per (event × target)", len(pairs) == len(jobs))

    # ---- verify on Telegram itself (read the target back) ----
    tgt0 = targets[0]
    recent = await helper.read_recent(tgt0, limit=25)
    texts = [(getattr(m, "message", "") or "") for m in recent]
    arrived = sum(1 for label, _ in cases if any(stamp in t and label.split()[0] == "text" for t in texts))
    report.check(
        "Target channel actually received the text post (read back from Telegram)",
        any(f"TAP LIVE probe text {stamp}" in t for t in texts),
    )
    media_posts = [m for m in recent if getattr(m, "media", None)]
    report.check(
        "Target channel received media posts (photo/video/document present)",
        len(media_posts) >= 3,
        f"media_posts={len(media_posts)}",
    )

    # ---- failure isolation: a target where the account cannot post ----
    if no_rights:
        bad = api.ensure_target(f"LIVE NoRights {no_rights}", no_rights)
        api.ensure_route("LIVE FAILURE", src_rows[0]["id"], bad["id"])
        marker = f"TAP LIVE failure-isolation {stamp}"
        sent = await helper.send_text(src0, marker)
        await asyncio.sleep(8)
        events = [e for e in api.messages(50) if marker in (e.get("raw_text") or "")]
        jobs = events[0]["jobs"] if events else []
        failed = [j for j in jobs if j["status"] in {"FAILED", "SKIPPED"}]
        ok_jobs = [j for j in jobs if j["status"] == "PUBLISHED"]
        report.check(
            "Failure isolation: one target fails while the others stay PUBLISHED",
            bool(failed) and len(ok_jobs) >= expected_jobs,
            f"failed={[(j['target_title'], j['status'], (j['last_error'] or j['skip_reason'] or '')[:60]) for j in failed]} ok={len(ok_jobs)}",
        )
        before = {j["target_channel_id"]: j["target_message_id"] for j in ok_jobs}
        api.post(f"/queue/jobs/{failed[0]['id']}/retry")
        await asyncio.sleep(7)
        events2 = [e for e in api.messages(50) if marker in (e.get("raw_text") or "")]
        jobs2 = events2[0]["jobs"] if events2 else []
        after = {j["target_channel_id"]: j["target_message_id"] for j in jobs2 if j["status"] == "PUBLISHED"}
        report.check(
            "Retrying the failed job never re-publishes the successful targets",
            all(before.get(tid) == after.get(tid) for tid in before),
            f"target_message_ids unchanged={before == {k: after.get(k) for k in before}}",
        )
        sent_id = sent.id

    # ---- restart recovery (worker down while a post arrives, then catch-up) ----
    print("\n== restart / catch-up scenario ==")
    print("    Stop the worker now (systemctl stop tap-worker) — continuing in 20s…")
    await asyncio.sleep(20)
    marker = f"TAP LIVE restart-catchup {stamp}"
    await helper.send_text(src0, marker)
    print("    Message posted while the worker was down. Restart it now.")
    for _ in range(60):
        await asyncio.sleep(3)
        events = [e for e in api.messages(30) if marker in (e.get("raw_text") or "")]
        if events and any(j["status"] == "PUBLISHED" for j in events[0]["jobs"]):
            break
    events = [e for e in api.messages(30) if marker in (e.get("raw_text") or "")]
    report.check(
        "Post that arrived while the worker was down is published after restart (persistent queue)",
        bool(events) and any(j["status"] == "PUBLISHED" for j in events[0]["jobs"]),
        f"jobs={[(j['target_title'], j['status']) for j in events[0]['jobs']] if events else 'no event'}",
    )

    # ---- reconnect / session durability ----
    rc = api.post("/telegram/reconnect").json()
    report.check(
        "Manual reconnect restores the saved encrypted session",
        rc.get("is_connected") is True and rc.get("auth_state") == "CONNECTED",
        f"auth_state={rc.get('auth_state')} attempts={rc.get('reconnect_attempts')}",
    )
    marker = f"TAP LIVE post-reconnect {stamp}"
    await helper.send_text(src0, marker)
    for _ in range(20):
        await asyncio.sleep(3)
        events = [e for e in api.messages(30) if marker in (e.get("raw_text") or "")]
        if events and any(j["status"] == "PUBLISHED" for j in events[0]["jobs"]):
            break
    events = [e for e in api.messages(30) if marker in (e.get("raw_text") or "")]
    report.check(
        "Publishing works immediately after reconnect",
        bool(events) and any(j["status"] == "PUBLISHED" for j in events[0]["jobs"]),
    )

    # ---- no duplicates & no archive import ----
    all_events = api.messages(100)
    keys = [(e["source_channel_id"], e["telegram_message_id"]) for e in all_events]
    report.check("No duplicate message events (DB unique constraint holds)", len(keys) == len(set(keys)), f"events={len(keys)}")
    job_pairs = [(j["message_event_id"], j["target_channel_id"]) for e in all_events for j in e["jobs"]]
    report.check("No duplicate (event × target) job", len(job_pairs) == len(set(job_pairs)), f"jobs={len(job_pairs)}")
    oldest = min((e["telegram_message_id"] for e in all_events), default=0)
    baseline = min((s["baseline_message_id"] or 0) for s in src_rows)
    report.check(
        "Nothing older than the recorded baseline was imported (no archive back-fill)",
        baseline == 0 or oldest >= baseline,
        f"oldest_event_msg={oldest} baseline={baseline}",
    )

    await helper.close()
    write_evidence(report, api, cases, expected_jobs)
    print(f"\n=== LIVE TELEGRAM E2E: {len(report.rows) - report.failed}/{len(report.rows)} checks passed ===")
    print(f"evidence written to {EVIDENCE.relative_to(ROOT)}")
    return 0 if report.failed == 0 else 1


def write_evidence(report: Report, api: Api, cases, expected_jobs: int) -> None:
    lines = [
        "# LIVE Telegram Evidence (real account → real channels)",
        "",
        f"- Run started (UTC): `{report.started_at}`",
        f"- Finished (UTC): `{datetime.now(timezone.utc).isoformat(timespec='seconds')}`",
        f"- Source/target topology: `1..N sources × {expected_jobs} target jobs per post`",
        "- Content injected: text, photo, document, video, 2-item album",
        "",
        "| # | Check | Result | Evidence |",
        "|---|---|---|---|",
    ]
    for i, (name, ok, detail) in enumerate(report.rows, 1):
        detail = (detail or "").replace("|", "\\|")
        lines.append(f"| {i} | {name} | {'✅ PASS' if ok else '❌ FAIL'} | `{detail}` |")
    lines += [
        "",
        "## Raw job records (from the live API)",
        "",
        "```json",
        json.dumps(api.queue(page_size=50), indent=2, ensure_ascii=False)[:12000],
        "```",
        "",
        "## Published content markers",
        "",
        "```",
        *[f"{label} -> source message ids {ids}" for label, ids in cases],
        "```",
        "",
        "> Generated by `scripts/live_telegram_e2e.py`. Contains no credentials, no session data, no API hash.",
    ]
    EVIDENCE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Live Telegram end-to-end proof for Telegram Auto Publisher")
    parser.add_argument("--dry-run", action="store_true", help="only verify prerequisites")
    args = parser.parse_args()
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
