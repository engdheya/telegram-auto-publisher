"""Route filter evaluation and text/caption transformation engine."""

from dataclasses import dataclass

from app.models import MessageEvent, RouteFilter
from app.repositories.route_repo import RouteRepository
from app.telegram.formatter import transform_text_and_entities


@dataclass
class FilterDecision:
    allowed: bool
    skip_reason: str | None = None
    transformed_text: str = ""
    transformed_entities_json: str = "[]"


class FilterEngine:
    @staticmethod
    def evaluate(event: MessageEvent, route_filter: RouteFilter | None) -> FilterDecision:
        # 1. Respect Telegram content protection unconditionally
        if event.is_protected_content:
            return FilterDecision(
                allowed=False,
                skip_reason=event.protection_reason
                or "PROTECTED_CONTENT_NOFORWARDS: Source restricts forwarding/reuse.",
            )

        # 2. Unsupported Telegram service/poll/game media
        if event.content_type == "unsupported":
            return FilterDecision(
                allowed=False,
                skip_reason="UNSUPPORTED_CONTENT_TYPE: Telegram message type is not publishable media/text.",
            )

        cfg = RouteRepository.filter_to_payload(route_filter)

        # 3. Allowed content types check
        if cfg.allowed_content_types and event.content_type not in cfg.allowed_content_types:
            return FilterDecision(
                allowed=False,
                skip_reason=f"CONTENT_TYPE_FILTERED: '{event.content_type}' is disabled on this route.",
            )

        # 4. Allowed file extensions check (applies when media items exist and allowed_extensions is non-empty)
        if cfg.allowed_extensions and event.media_items:
            normalized_allowed = {
                ext.lower() if ext.startswith(".") else f".{ext.lower()}"
                for ext in cfg.allowed_extensions
                if ext.strip()
            }
            if normalized_allowed:
                for media in event.media_items:
                    ext = (media.file_ext or "").lower()
                    if ext not in normalized_allowed:
                        return FilterDecision(
                            allowed=False,
                            skip_reason=f"EXTENSION_FILTERED: File extension '{ext or 'none'}' not in allowed list {sorted(normalized_allowed)}.",
                        )

        raw_text = (event.raw_text or "").strip()
        lowered_text = raw_text.lower()

        # 5. Excluded keywords (any match -> skip)
        for bad_kw in cfg.exclude_keywords:
            kw = bad_kw.strip()
            if kw and kw.lower() in lowered_text:
                return FilterDecision(
                    allowed=False,
                    skip_reason=f"EXCLUDED_KEYWORD: Matched blocked keyword '{kw}'.",
                )

        # 6. Included keywords (when configured, at least one must match)
        active_inc = [kw.strip() for kw in cfg.include_keywords if kw and kw.strip()]
        if active_inc:
            if not any(kw.lower() in lowered_text for kw in active_inc):
                return FilterDecision(
                    allowed=False,
                    skip_reason="MISSING_INCLUDED_KEYWORD: Post did not contain any required keywords.",
                )

        # 7. Min / Max text length bounds
        text_len = len(raw_text)
        if cfg.min_text_length is not None and text_len < cfg.min_text_length:
            return FilterDecision(
                allowed=False,
                skip_reason=f"TEXT_TOO_SHORT: Length {text_len} < minimum {cfg.min_text_length}.",
            )
        if cfg.max_text_length is not None and text_len > cfg.max_text_length:
            return FilterDecision(
                allowed=False,
                skip_reason=f"TEXT_TOO_LONG: Length {text_len} > maximum {cfg.max_text_length}.",
            )

        # 8. Transform text (prefix, suffix, target signature, strip URLs) & shift entities
        transformed_text, transformed_entities_json = transform_text_and_entities(
            event.raw_text,
            event.entities_json,
            prefix_text=cfg.prefix_text,
            suffix_text=cfg.suffix_text,
            target_signature=cfg.target_signature,
            strip_urls=cfg.strip_urls,
        )

        # Telegram caption limit is 1024 chars for media/albums, 4096 for pure text
        max_tg_limit = 4096 if event.content_type == "text" else 1024
        if len(transformed_text) > max_tg_limit:
            transformed_text = transformed_text[: max_tg_limit - 1] + "…"

        return FilterDecision(
            allowed=True,
            transformed_text=transformed_text,
            transformed_entities_json=transformed_entities_json,
        )
