from __future__ import annotations

import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Dict, List, Optional

import requests


def _retry_after_seconds(response: requests.Response) -> float:
    header = response.headers.get("Retry-After")
    if not header:
        return 0.0
    try:
        return max(float(header), 0.0)
    except Exception:
        pass
    try:
        dt = parsedate_to_datetime(header)
        now = datetime.now(timezone.utc)
        return max((dt - now).total_seconds(), 0.0)
    except Exception:
        return 0.0


def fetch_json_with_retries(
    url: str,
    *,
    timeout_sec: int = 15,
    retry_max: int = 3,
    retry_backoff_sec: float = 0.5,
) -> List[Dict]:
    last_error: Optional[str] = None
    for attempt in range(retry_max + 1):
        try:
            response = requests.get(url, timeout=timeout_sec)

            if response.status_code == 429:
                if attempt == retry_max:
                    response.raise_for_status()
                wait = _retry_after_seconds(response)
                if wait <= 0:
                    wait = retry_backoff_sec * (2 ** attempt)
                time.sleep(wait)
                continue

            if 500 <= response.status_code < 600 and attempt < retry_max:
                time.sleep(retry_backoff_sec * (2 ** attempt))
                continue

            response.raise_for_status()
            payload = response.json()
            if isinstance(payload, list):
                return [row for row in payload if isinstance(row, dict)]
            if isinstance(payload, dict):
                if isinstance(payload.get("data"), list):
                    return [row for row in payload["data"] if isinstance(row, dict)]
                if isinstance(payload.get("items"), list):
                    return [row for row in payload["items"] if isinstance(row, dict)]
                return [payload]
            return []
        except Exception as exc:
            last_error = str(exc)
            if attempt == retry_max:
                break
            time.sleep(retry_backoff_sec * (2 ** attempt))

    raise ValueError(f"Failed to fetch API data from {url}. Last error: {last_error}")
