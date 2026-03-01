from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import parse_qs, urlparse

import requests

from typing import Dict, List

from .common import fetch_json_with_retries


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return default


def _daily_from_openweather(city: str, api_key: str, timeout_sec: int) -> List[Dict]:
    url = "https://api.openweathermap.org/data/2.5/forecast"
    params = {"q": city, "appid": api_key, "units": "metric"}
    try:
        response = requests.get(url, params=params, timeout=timeout_sec)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise ValueError(f"OpenWeather request failed: {exc}") from exc

    try:
        data = response.json()
    except ValueError as exc:
        raise ValueError("OpenWeather returned invalid JSON payload.") from exc

    rows = data.get("list")
    if not isinstance(rows, list):
        raise ValueError("Unexpected OpenWeather payload: missing 'list' array.")

    by_date: Dict[str, Dict[str, Any]] = {}
    for entry in rows:
        ts = entry.get("dt")
        main = entry.get("main") or {}
        wind = entry.get("wind") or {}
        if ts is None:
            continue

        dt = datetime.fromtimestamp(_to_int(ts))
        key = dt.date().isoformat()
        bucket = by_date.setdefault(
            key,
            {
                "date": key,
                "temp_values": [],
                "humidity_values": [],
                "pressure_values": [],
                "wind_values": [],
                "precipitation_total": 0.0,
                "weather": None,
            },
        )

        bucket["temp_values"].append(_to_float(main.get("temp"), 0.0))
        bucket["humidity_values"].append(_to_float(main.get("humidity"), 0.0))
        bucket["pressure_values"].append(_to_float(main.get("pressure"), 0.0))
        bucket["wind_values"].append(_to_float(wind.get("speed"), 0.0))
        bucket["precipitation_total"] += _to_float((entry.get("rain") or {}).get("3h"), 0.0)

        weather_items = entry.get("weather") or []
        if bucket["weather"] is None and isinstance(weather_items, list) and weather_items:
            first = weather_items[0] or {}
            bucket["weather"] = first.get("main")

    out: List[Dict] = []
    for _, row in sorted(by_date.items()):
        temp_values = row["temp_values"]
        humidity_values = row["humidity_values"]
        pressure_values = row["pressure_values"]
        wind_values = row["wind_values"]
        temp_mean = sum(temp_values) / len(temp_values) if temp_values else 0.0
        out.append(
            {
                "date": row["date"],
                "temp_mean": round(temp_mean, 3),
                "humidity": round(sum(humidity_values) / len(humidity_values), 3) if humidity_values else 0.0,
                "pressure": round(sum(pressure_values) / len(pressure_values), 3) if pressure_values else 0.0,
                "wind_speed": round(sum(wind_values) / len(wind_values), 3) if wind_values else 0.0,
                "precipitation": round(_to_float(row["precipitation_total"], 0.0), 3),
                "weather": row["weather"] or "",
                "weather_score": round(temp_mean, 3),
                "source": "future",
            }
        )
    if not out:
        raise ValueError("OpenWeather payload did not contain usable weather rows.")

    return out


def _daily_value(series: Any, idx: int) -> float:
    if not isinstance(series, list):
        return 0.0
    if idx < 0 or idx >= len(series):
        return 0.0
    return _to_float(series[idx], 0.0)


def _daily_from_open_meteo(lat: float, lon: float, days: int, timeout_sec: int) -> List[Dict]:
    end_date = datetime.today().date()
    start_date = end_date - timedelta(days=max(days, 1))

    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": str(start_date),
        "end_date": str(end_date),
        "daily": [
            "temperature_2m_max",
            "temperature_2m_min",
            "temperature_2m_mean",
            "relative_humidity_2m_mean",
            "surface_pressure_mean",
            "windspeed_10m_max",
            "precipitation_sum",
        ],
        "timezone": "America/New_York",
    }

    try:
        response = requests.get(url, params=params, timeout=timeout_sec)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise ValueError(f"Open-Meteo request failed: {exc}") from exc

    try:
        payload = response.json()
    except ValueError as exc:
        raise ValueError("Open-Meteo returned invalid JSON payload.") from exc

    daily = payload.get("daily") or {}
    dates = daily.get("time") or []
    if not isinstance(dates, list) or not dates:
        raise ValueError("Unexpected Open-Meteo payload: missing daily.time values.")

    out: List[Dict] = []
    for idx, date in enumerate(dates):
        temp_mean = _daily_value(daily.get("temperature_2m_mean"), idx)
        out.append(
            {
                "date": str(date),
                "temp_max": _daily_value(daily.get("temperature_2m_max"), idx),
                "temp_min": _daily_value(daily.get("temperature_2m_min"), idx),
                "temp_mean": temp_mean,
                "humidity": _daily_value(daily.get("relative_humidity_2m_mean"), idx),
                "pressure": _daily_value(daily.get("surface_pressure_mean"), idx),
                "wind_speed": _daily_value(daily.get("windspeed_10m_max"), idx),
                "precipitation": _daily_value(daily.get("precipitation_sum"), idx),
                "weather_score": round(temp_mean, 3),
                "source": "past",
            }
        )

    if not out:
        raise ValueError("Open-Meteo payload did not contain usable weather rows.")

    return out


def _fetch_notebook_equivalent_weather(url: str, timeout_sec: int) -> List[Dict]:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)

    city = (query.get("city", ["OHIO"])[0] or "OHIO").strip()
    lat = _to_float(query.get("lat", ["40.1088"])[0], 40.1088)
    lon = _to_float(query.get("lon", ["-82.9742"])[0], -82.9742)
    days = _to_int(query.get("days", ["4"])[0], 4)
    api_key = (query.get("api_key", [""])[0] or os.getenv("OPENWEATHER_API_KEY") or "").strip()
    past = _daily_from_open_meteo(lat=lat, lon=lon, days=days, timeout_sec=timeout_sec)

    if not api_key:
        return past

    try:
        future = _daily_from_openweather(city=city, api_key=api_key, timeout_sec=timeout_sec)
    except ValueError:
        return past

    return past + future


def fetch_weather_rows(
    url: str,
    *,
    timeout_sec: int = 15,
    retry_max: int = 3,
    retry_backoff_sec: float = 0.5,
) -> List[Dict]:
    if url.startswith("builtin://weather"):
        return _fetch_notebook_equivalent_weather(url, timeout_sec=timeout_sec)

    return fetch_json_with_retries(
        url,
        timeout_sec=timeout_sec,
        retry_max=retry_max,
        retry_backoff_sec=retry_backoff_sec,
    )
