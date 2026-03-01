from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional, Tuple


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_iso_date(value: object) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if "T" in text:
        return text.split("T", 1)[0]
    return text


def _to_int(value: object, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return default


def _to_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _clip(value: float, low: float, high: float) -> float:
    if value < low:
        return low
    if value > high:
        return high
    return value


def _normalize(values: Dict[Tuple[str, str, int], float]) -> Dict[Tuple[str, str, int], float]:
    if not values:
        return {}
    series = list(values.values())
    min_v = min(series)
    max_v = max(series)
    if max_v - min_v < 1e-9:
        return {key: 0.0 for key in values}

    result: Dict[Tuple[str, str, int], float] = {}
    for key, value in values.items():
        scaled = ((value - min_v) / (max_v - min_v)) * 2.0 - 1.0
        result[key] = round(_clip(scaled, -1.0, 1.0), 4)
    return result


def _index_sales_rows(sales_rows: Iterable[Dict]) -> Dict[Tuple[str, str, int], Dict]:
    indexed: Dict[Tuple[str, str, int], Dict] = {}
    for row in sales_rows:
        date = _to_iso_date(row.get("date") or row.get("day") or row.get("timestamp"))
        product_id = str(row.get("product_id") or row.get("sku") or "").strip()
        location_id = _to_int(row.get("location_id") or row.get("store_id") or row.get("location"), -1)
        if not date or not product_id or location_id < 0:
            continue

        units = _to_float(row.get("units") or row.get("sales_units") or row.get("qty") or row.get("quantity"), 0.0)
        indexed[(date, product_id, location_id)] = {
            "date": date,
            "product_id": product_id,
            "location_id": location_id,
            "units": max(units, 0.0),
            "source_ts": str(row.get("source_ts") or row.get("timestamp") or _now_iso()),
            "ingested_ts": _now_iso(),
        }
    return indexed


def _index_signal_rows(
    rows: Iterable[Dict],
    *,
    signal_field: str,
    fallback_fields: List[str],
) -> Dict[Tuple[str, Optional[str], Optional[int]], float]:
    indexed: Dict[Tuple[str, Optional[str], Optional[int]], float] = {}
    for row in rows:
        date = _to_iso_date(row.get("date") or row.get("day") or row.get("timestamp"))
        if not date:
            continue

        product = row.get("product_id") or row.get("sku")
        location = row.get("location_id") or row.get("store_id") or row.get("location")
        product_id = str(product).strip() if product is not None else None
        location_id = _to_int(location, -1) if location is not None else None
        if location is not None and location_id == -1:
            location_id = None

        raw = row.get(signal_field)
        if raw is None:
            for name in fallback_fields:
                if row.get(name) is not None:
                    raw = row.get(name)
                    break

        indexed[(date, product_id, location_id)] = _to_float(raw, 0.0)
    return indexed


def build_history_from_source_rows(
    *,
    sales_rows: List[Dict],
    weather_rows: List[Dict],
    social_rows: List[Dict],
    location_ids: List[int],
) -> List[Dict]:
    sales_index = _index_sales_rows(sales_rows)
    if not sales_index:
        return []

    weather_index = _index_signal_rows(
        weather_rows,
        signal_field="weather_score",
        fallback_fields=["weather_index", "weather", "temp_score", "temperature"],
    )
    social_index = _index_signal_rows(
        social_rows,
        signal_field="social_signal",
        fallback_fields=["social_score", "trend_score", "trend", "sentiment_score"],
    )

    weather_values: Dict[Tuple[str, str, int], float] = {}
    social_values: Dict[Tuple[str, str, int], float] = {}

    for key in sales_index:
        date, product_id, location_id = key

        weather_raw = weather_index.get((date, product_id, location_id))
        if weather_raw is None:
            weather_raw = weather_index.get((date, None, location_id))
        if weather_raw is None:
            weather_raw = weather_index.get((date, product_id, None))
        if weather_raw is None:
            weather_raw = weather_index.get((date, None, None), 0.0)

        social_raw = social_index.get((date, product_id, location_id))
        if social_raw is None:
            social_raw = social_index.get((date, None, location_id))
        if social_raw is None:
            social_raw = social_index.get((date, product_id, None))
        if social_raw is None:
            social_raw = social_index.get((date, None, None), 0.0)

        weather_values[key] = weather_raw
        social_values[key] = social_raw

    weather_norm = _normalize(weather_values)
    social_norm = _normalize(social_values)

    history: List[Dict] = []
    for key, sales in sales_index.items():
        date, product_id, location_id = key
        if location_ids and location_id not in location_ids:
            continue

        history.append(
            {
                "date": date,
                "product_id": product_id,
                "location_id": int(location_id),
                "units": round(_to_float(sales.get("units"), 0.0), 2),
                "weather_score": round(weather_norm.get(key, 0.0), 4),
                "social_signal": round(social_norm.get(key, 0.0), 4),
                "event_score": 0.0,
                "source_ts": sales.get("source_ts"),
                "ingested_ts": sales.get("ingested_ts"),
            }
        )

    history.sort(key=lambda row: (row["date"], row["location_id"]))
    return history
