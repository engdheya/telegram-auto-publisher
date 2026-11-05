"""Telethon formatting entity serialization, UTF-16 offset shifting, and text transformation."""

import json
import re
from typing import Any

from telethon.tl import types as tl_types

URL_PATTERN = re.compile(r"https?://\S+", re.IGNORECASE)

ENTITY_CLASS_TO_TYPE: dict[type, str] = {
    tl_types.MessageEntityBold: "bold",
    tl_types.MessageEntityItalic: "italic",
    tl_types.MessageEntityUnderline: "underline",
    tl_types.MessageEntityStrike: "strike",
    tl_types.MessageEntityCode: "code",
    tl_types.MessageEntityPre: "pre",
    tl_types.MessageEntityTextUrl: "text_url",
    tl_types.MessageEntitySpoiler: "spoiler",
    tl_types.MessageEntityBlockquote: "blockquote",
}

TYPE_TO_ENTITY_CLASS: dict[str, type] = {v: k for k, v in ENTITY_CLASS_TO_TYPE.items()}


def utf16_len(text: str) -> int:
    """Telegram MTProto entity offsets and lengths are measured in UTF-16 code units."""
    if not text:
        return 0
    return len(text.encode("utf-16-le")) // 2


def serialize_entities(entities: list[Any] | None) -> list[dict[str, Any]]:
    """Serialize Telethon MessageEntity objects (or dicts) into JSON-safe dictionaries."""
    if not entities:
        return []
    result: list[dict[str, Any]] = []
    for ent in entities:
        if isinstance(ent, dict):
            if "type" in ent and "offset" in ent and "length" in ent:
                result.append(dict(ent))
            continue
        ent_type = ENTITY_CLASS_TO_TYPE.get(type(ent))
        if not ent_type:
            continue
        item: dict[str, Any] = {
            "type": ent_type,
            "offset": int(getattr(ent, "offset", 0)),
            "length": int(getattr(ent, "length", 0)),
        }
        if ent_type == "pre":
            item["language"] = getattr(ent, "language", "") or ""
        elif ent_type == "text_url":
            item["url"] = getattr(ent, "url", "") or ""
        result.append(item)
    return result


def deserialize_entities(entities_data: list[dict[str, Any]] | str | None) -> list[Any]:
    """Reconstruct Telethon TL MessageEntity instances from JSON serialized list."""
    if not entities_data:
        return []
    if isinstance(entities_data, str):
        try:
            parsed = json.loads(entities_data)
        except Exception:
            return []
    else:
        parsed = entities_data

    rebuilt: list[Any] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        ent_type = item.get("type")
        offset = int(item.get("offset", 0))
        length = int(item.get("length", 0))
        if length <= 0 or offset < 0:
            continue
        cls = TYPE_TO_ENTITY_CLASS.get(str(ent_type))
        if cls is None:
            continue
        if ent_type == "pre":
            rebuilt.append(cls(offset=offset, length=length, language=str(item.get("language", ""))))
        elif ent_type == "text_url":
            url = str(item.get("url", ""))
            if url:
                rebuilt.append(cls(offset=offset, length=length, url=url))
        else:
            rebuilt.append(cls(offset=offset, length=length))
    return rebuilt


def transform_text_and_entities(
    raw_text: str | None,
    entities_json: str | None,
    *,
    prefix_text: str | None = None,
    suffix_text: str | None = None,
    target_signature: str | None = None,
    strip_urls: bool = False,
) -> tuple[str, str]:
    """
    Apply prefix, suffix, target signature, and optional URL stripping while shifting
    UTF-16 formatting entity offsets accurately.
    """
    base_text = raw_text or ""
    try:
        entities: list[dict[str, Any]] = json.loads(entities_json or "[]")
    except Exception:
        entities = []

    if strip_urls and base_text:
        base_text = URL_PATTERN.sub("", base_text).strip()
        # Drop text_url entities and clamp remaining entities within new bounds
        max_u16 = utf16_len(base_text)
        entities = [
            e
            for e in entities
            if e.get("type") != "text_url"
            and int(e.get("offset", 0)) + int(e.get("length", 0)) <= max_u16
        ]

    prefix_block = f"{prefix_text.strip()}\n\n" if prefix_text and prefix_text.strip() else ""
    suffix_parts: list[str] = []
    if suffix_text and suffix_text.strip():
        suffix_parts.append(suffix_text.strip())
    if target_signature and target_signature.strip():
        suffix_parts.append(target_signature.strip())
    suffix_block = ("\n\n" + "\n".join(suffix_parts)) if suffix_parts else ""

    if not base_text:
        combined = "\n\n".join(
            p for p in [prefix_text.strip() if prefix_text else "", *suffix_parts] if p
        )
        return combined, "[]"

    shift = utf16_len(prefix_block)
    shifted_entities: list[dict[str, Any]] = []
    for ent in entities:
        copied = dict(ent)
        copied["offset"] = int(copied.get("offset", 0)) + shift
        shifted_entities.append(copied)

    final_text = f"{prefix_block}{base_text}{suffix_block}"
    return final_text, json.dumps(shifted_entities, ensure_ascii=False)
