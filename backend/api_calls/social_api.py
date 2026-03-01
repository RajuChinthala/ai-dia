from __future__ import annotations

import random
from datetime import datetime, timedelta
from urllib.parse import parse_qs, urlparse

from typing import Dict, List

from .common import fetch_json_with_retries


def _to_int(text: str, default: int) -> int:
    try:
        return int(float(text))
    except Exception:
        return default


def _generate_notebook_like_social(url: str) -> List[Dict]:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)

    seed = _to_int((query.get("seed", ["42"])[0] or "42"), 42)
    days = max(_to_int((query.get("days", ["14"])[0] or "14"), 14), 1)

    rng = random.Random(seed)
    end = datetime.today().date()
    start = end - timedelta(days=days - 1)
    dates = [start + timedelta(days=offset) for offset in range(days)]

    events = [
        "Holiday Sale",
        "Product Launch",
        "Flash Sale",
        "Weekend Deal",
        "Social Media Challenge",
        "No Event",
        "No Event",
        "End of Year Promo",
        "Influencer Collab",
        "Weekend Special",
        "No Event",
        "Holiday Gift Guide",
        "Pre-Christmas Sale",
        "Last Minute Deals",
    ]

    rows: List[Dict] = []
    for index, day in enumerate(dates):
        event_name = events[index % len(events)]
        event_flag = 0 if event_name == "No Event" else 1
        social_mentions = rng.randint(50, 500)
        trend_score = rng.randint(100, 1000)

        rows.append(
            {
                "date": day.isoformat(),
                "event_name": event_name,
                "social_mentions": social_mentions,
                "event_flag": event_flag,
                "trend_score": trend_score,
                "social_signal": float(trend_score),
            }
        )

    return rows


def fetch_social_rows(
    url: str,
    *,
    timeout_sec: int = 15,
    retry_max: int = 3,
    retry_backoff_sec: float = 0.5,
) -> List[Dict]:
    if url.startswith("builtin://social"):
        return _generate_notebook_like_social(url)

    return fetch_json_with_retries(
        url,
        timeout_sec=timeout_sec,
        retry_max=retry_max,
        retry_backoff_sec=retry_backoff_sec,
    )
