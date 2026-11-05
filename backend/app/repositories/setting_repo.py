"""System settings repository."""

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import SystemSetting


class SettingRepository:
    @staticmethod
    def get_value(db: Session, key: str, default: Any = None) -> Any:
        row = db.execute(select(SystemSetting).where(SystemSetting.key == key)).scalar_one_or_none()
        if row is None:
            return default
        try:
            return json.loads(row.value_json)
        except Exception:
            return row.value_json

    @staticmethod
    def set_value(
        db: Session,
        key: str,
        value: Any,
        *,
        category: str = "general",
        description: str | None = None,
        updated_by: str = "system",
    ) -> SystemSetting:
        row = db.execute(select(SystemSetting).where(SystemSetting.key == key)).scalar_one_or_none()
        encoded = json.dumps(value, ensure_ascii=False)
        if row is None:
            row = SystemSetting(
                key=key,
                value_json=encoded,
                category=category,
                description=description,
                updated_by=updated_by,
            )
            db.add(row)
        else:
            row.value_json = encoded
            row.updated_by = updated_by
            if description is not None:
                row.description = description
        return row

    @staticmethod
    def list_all(db: Session, include_runtime: bool = False) -> list[dict[str, Any]]:
        stmt = select(SystemSetting).order_by(SystemSetting.category.asc(), SystemSetting.key.asc())
        if not include_runtime:
            stmt = stmt.where(SystemSetting.category != "runtime")
        rows = db.execute(stmt).scalars().all()
        result: list[dict[str, Any]] = []
        for r in rows:
            try:
                val = json.loads(r.value_json)
            except Exception:
                val = r.value_json
            result.append(
                {
                    "key": r.key,
                    "value": val,
                    "category": r.category,
                    "description": r.description,
                    "updated_by": r.updated_by,
                    "updated_at": r.updated_at.isoformat() if r.updated_at else None,
                }
            )
        return result
