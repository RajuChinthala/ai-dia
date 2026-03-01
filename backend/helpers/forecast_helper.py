from __future__ import annotations

from typing import Dict, List

from ..api_calls import fetch_sales_rows, fetch_social_rows, fetch_weather_rows
from .merge_history import build_history_from_source_rows


def _remap_history_locations(history: List[Dict], target_location_ids: List[int]) -> List[Dict]:
    if not history or not target_location_ids:
        return history

    source_location_ids = sorted({int(row.get("location_id", -1)) for row in history if "location_id" in row})
    if not source_location_ids:
        return history

    mapping: Dict[int, int] = {}
    for idx, source_id in enumerate(source_location_ids):
        mapping[source_id] = int(target_location_ids[idx % len(target_location_ids)])

    remapped: List[Dict] = []
    for row in history:
        source_id = int(row.get("location_id", -1))
        target_id = mapping.get(source_id)
        if target_id is None:
            continue
        updated = row.copy()
        updated["location_id"] = target_id
        remapped.append(updated)

    return remapped


def build_history_and_forecast_from_apis(
    *,
    product_id: str,
    location_ids: List[int],
    sales_api_url: str,
    weather_api_url: str,
    social_api_url: str | None = None,
    seasonal_api_url: str | None = None,
    horizon: int,
    api_timeout_sec: int = 15,
    retry_max: int = 3,
    retry_backoff_sec: float = 0.5,
) -> Dict:
    trend_url = (seasonal_api_url or social_api_url or "").strip()
    if not trend_url:
        raise ValueError("Either social_api_url or seasonal_api_url must be provided.")

    sales_rows = fetch_sales_rows(
        sales_api_url,
        timeout_sec=api_timeout_sec,
        retry_max=retry_max,
        retry_backoff_sec=retry_backoff_sec,
    )
    weather_rows = fetch_weather_rows(
        weather_api_url,
        timeout_sec=api_timeout_sec,
        retry_max=retry_max,
        retry_backoff_sec=retry_backoff_sec,
    )
    social_rows = fetch_social_rows(
        trend_url,
        timeout_sec=api_timeout_sec,
        retry_max=retry_max,
        retry_backoff_sec=retry_backoff_sec,
    )

    history = build_history_from_source_rows(
        sales_rows=sales_rows,
        weather_rows=weather_rows,
        social_rows=social_rows,
        location_ids=location_ids,
    )

    if not history and location_ids:
        unfiltered_history = build_history_from_source_rows(
            sales_rows=sales_rows,
            weather_rows=weather_rows,
            social_rows=social_rows,
            location_ids=[],
        )
        history = _remap_history_locations(unfiltered_history, location_ids)

    if not history:
        return {"history": [], "forecasts": []}

    return {
        "history": history,
        "forecasts": [],
    }
