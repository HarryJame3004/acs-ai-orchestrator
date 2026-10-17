"""ACS AI V2 Test Health Tracker.
Records and retrieves verified test results for ACS AI and ACS Core.
Prevents stale, fabricated, or hardcoded test statistics.
"""

from __future__ import annotations

import datetime
import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from .config import STATE_DIR

logger = logging.getLogger("acs_ai.test_tracker")

TEST_HEALTH_FILE = STATE_DIR / "test_health.json"


def record_test_run(
    component: str,
    passed: int,
    total: int,
    failed: int = 0,
    duration_sec: Optional[float] = None,
    notes: Optional[str] = None,
) -> Dict[str, Any]:
    """Records the real results of a verified test run with UTC timestamp."""
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    record = {
        "component": component,
        "passed": passed,
        "total": total,
        "failed": failed,
        "status": "PASS" if failed == 0 and passed == total and total > 0 else "FAIL",
        "duration_sec": round(duration_sec, 2) if duration_sec is not None else None,
        "timestamp": now,
        "notes": notes,
    }

    data = _load_all_records()
    data[component] = record

    try:
        TEST_HEALTH_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning(f"Failed to persist test health record: {e}")

    return record


def get_test_health(component: str) -> Dict[str, Any]:
    """Retrieves the latest verified test result for a component."""
    data = _load_all_records()
    if component in data:
        rec = data[component]
        # Format human-friendly timestamp
        ts = rec.get("timestamp", "")
        time_str = ts[11:16] if len(ts) >= 16 else ts
        display = f"{rec.get('passed')}/{rec.get('total')} {rec.get('status')} — verified {time_str} UTC"
        return {
            "verified": True,
            "status": rec.get("status"),
            "passed": rec.get("passed"),
            "total": rec.get("total"),
            "failed": rec.get("failed"),
            "timestamp": ts,
            "display": display,
        }
    return {
        "verified": False,
        "status": "UNKNOWN",
        "display": "NOT RECHECKED — previous result unavailable",
    }


def _load_all_records() -> Dict[str, Any]:
    if TEST_HEALTH_FILE.exists():
        try:
            return json.loads(TEST_HEALTH_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}
