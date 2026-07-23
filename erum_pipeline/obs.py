"""Minimal structured observability for E6."""
from __future__ import annotations

import json
import time
from typing import Any


def emit_metric(event: str, **fields: Any) -> dict:
    payload = {"ts": int(time.time()), "event": event, **fields}
    print(json.dumps(payload, ensure_ascii=False))
    return payload
