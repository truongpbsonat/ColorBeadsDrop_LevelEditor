from __future__ import annotations

import uuid


def short_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:6]}"


def safe_int(value: str, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def safe_float(value: str, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default
