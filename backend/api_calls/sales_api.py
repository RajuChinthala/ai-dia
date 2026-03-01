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


def _generate_notebook_like_sales(url: str) -> List[Dict]:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)

    seed = _to_int((query.get("seed", ["42"])[0] or "42"), 42)
    days = max(_to_int((query.get("days", ["14"])[0] or "14"), 14), 1)
    product_count = max(_to_int((query.get("products", ["5"])[0] or "5"), 5), 1)

    rng = random.Random(seed)
    end = datetime.today().date()
    start = end - timedelta(days=days - 1)
    dates = [start + timedelta(days=offset) for offset in range(days)]

    location_coordinates = {
        1: {"lat": 40.8037, "lon": -80.9575},
        2: {"lat": 39.5673, "lon": -82.0911},
        3: {"lat": 40.0805, "lon": -84.3418},
        4: {"lat": 40.4173, "lon": -81.2330},
        5: {"lat": 40.0000, "lon": -83.0000},
        6: {"lat": 39.9622, "lon": -83.0007},
        7: {"lat": 40.0264, "lon": -82.9669},
        8: {"lat": 39.8973, "lon": -83.0769},
        9: {"lat": 39.9202, "lon": -83.1091},
    }

    rows: List[Dict] = []
    for product_id in range(1, product_count + 1):
        sku = f"SKU-00{product_id}"
        for location_id, coord in location_coordinates.items():
            baseline = rng.randint(5, 20)
            for day in dates:
                sold = max(0, int(round(baseline + rng.gauss(0, 5))))
                available = int(max(0, round(sold * rng.uniform(1.1, 1.5))))
                rows.append(
                    {
                        "date": day.isoformat(),
                        "product_id": str(product_id),
                        "sku": sku,
                        "location_id": location_id,
                        "latitude": coord["lat"],
                        "longitude": coord["lon"],
                        "total_products_sold": sold,
                        "available_quantity": available,
                        "total_product_counts": sold + available,
                        "units": sold,
                    }
                )

    return rows


def fetch_sales_rows(
    url: str,
    *,
    timeout_sec: int = 15,
    retry_max: int = 3,
    retry_backoff_sec: float = 0.5,
) -> List[Dict]:
    if url.startswith("builtin://sales"):
        return _generate_notebook_like_sales(url)

    return fetch_json_with_retries(
        url,
        timeout_sec=timeout_sec,
        retry_max=retry_max,
        retry_backoff_sec=retry_backoff_sec,
    )
