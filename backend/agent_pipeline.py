from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Tuple

from . import allocation


def _moving_average(values: List[float], window: int) -> float:
    if not values:
        return 0.0
    if len(values) < window:
        return sum(values) / len(values)
    return sum(values[-window:]) / window


def _trend(values: List[float]) -> float:
    if len(values) < 2:
        return 0.0
    x_mean = (len(values) - 1) / 2
    y_mean = sum(values) / len(values)
    num = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
    den = sum((i - x_mean) ** 2 for i in range(len(values)))
    return num / den if den else 0.0


def _seasonality(values: List[float], period: int = 7) -> float:
    if len(values) < period * 2:
        return 0.0
    current = sum(values[-period:]) / period
    prior = sum(values[-2 * period : -period]) / period
    return current - prior


def _specialist_signal_agent(history: List[Dict], product_id: str) -> Dict[int, Dict[str, float]]:
    sales: Dict[int, List[float]] = defaultdict(list)
    weather: Dict[int, List[float]] = defaultdict(list)
    social: Dict[int, List[float]] = defaultdict(list)

    for row in history:
        if str(row.get("product_id")) != str(product_id):
            continue
        loc_id = int(row.get("location_id"))
        sales[loc_id].append(float(row.get("units", 0.0)))
        weather[loc_id].append(float(row.get("weather_score", 0.0)))
        social[loc_id].append(float(row.get("social_signal", 0.0)))

    outputs: Dict[int, Dict[str, float]] = {}
    for loc_id, sales_values in sales.items():
        sales_base_daily = _moving_average(sales_values, window=7)
        sales_trend_daily = _trend(sales_values)
        seasonal_weekly_delta = _seasonality(sales_values, period=7)
        weather_daily_impact = _moving_average(weather[loc_id], window=7) * -1.5
        social_daily_impact = _moving_average(social[loc_id], window=7) * 2.0
        outputs[loc_id] = {
            "sales_base_daily": round(sales_base_daily, 3),
            "sales_trend_daily": round(sales_trend_daily, 3),
            "seasonal_weekly_delta": round(seasonal_weekly_delta, 3),
            "weather_daily_impact": round(weather_daily_impact, 3),
            "social_daily_impact": round(social_daily_impact, 3),
        }
    return outputs


def _final_forecast_agent(
    specialist_outputs: Dict[int, Dict[str, float]],
    locations: List[Dict],
    horizon: int,
) -> Tuple[List[Dict], List[Dict]]:
    enriched_locations = [loc.copy() for loc in locations]
    diagnostics: List[Dict] = []

    for loc in enriched_locations:
        loc_id = int(loc["location_id"])
        s = specialist_outputs.get(
            loc_id,
            {
                "sales_base_daily": 0.0,
                "sales_trend_daily": 0.0,
                "seasonal_weekly_delta": 0.0,
                "weather_daily_impact": 0.0,
                "social_daily_impact": 0.0,
            },
        )

        daily = (
            s["sales_base_daily"]
            + s["sales_trend_daily"]
            + s["seasonal_weekly_delta"]
            + s["weather_daily_impact"]
            + s["social_daily_impact"]
        )
        daily = max(daily, 0.0)
        period_forecast = int(round(daily * horizon))
        loc["demand_forecast"] = period_forecast

        diagnostics.append(
            {
                "location_id": loc_id,
                "sales_base_daily": round(s["sales_base_daily"], 2),
                "sales_trend_daily": round(s["sales_trend_daily"], 2),
                "seasonal_weekly_delta": round(s["seasonal_weekly_delta"], 2),
                "weather_daily_impact": round(s["weather_daily_impact"], 2),
                "social_daily_impact": round(s["social_daily_impact"], 2),
                "final_daily_forecast": round(daily, 2),
                "final_period_forecast": period_forecast,
            }
        )

    return enriched_locations, diagnostics


def run_agent_orchestrated_pipeline(
    product_id: str,
    inbound: int,
    locations: List[Dict],
    history: List[Dict],
    horizon: int = 7,
) -> Dict:
    specialist = _specialist_signal_agent(history, product_id)
    final_locations, diagnostics = _final_forecast_agent(specialist, locations, horizon)

    allocation_result = allocation.optimize_allocation(product_id, inbound, final_locations)

    return {
        "product_id": product_id,
        "horizon": horizon,
        "allocation_mode": "deterministic",
        "specialist_outputs": diagnostics,
        "allocations": allocation_result["allocations"],
        "inbound_remaining": allocation_result["inbound_remaining"],
        "estimated_total_cost": allocation_result["estimated_total_cost"],
        "fill_rate": allocation_result["fill_rate"],
    }


def run_pipeline_with_precomputed_forecast(
    product_id: str,
    inbound: int,
    locations: List[Dict],
    forecast_rows: List,
    horizon: int = 7,
) -> Dict:
    def _as_float(value, default: float = 0.0) -> float:
        if value is None:
            return default
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    forecast_map = {int(row.location_id): row for row in forecast_rows}
    final_locations = [loc.copy() for loc in locations]
    diagnostics: List[Dict] = []

    for loc in final_locations:
        loc_id = int(loc["location_id"])
        forecast = forecast_map.get(loc_id)

        if forecast is None:
            final_daily = 0.0
            final_period = 0
            trend_hint = 0.0
            seasonality_hint = 0.0
        else:
            final_daily = max(_as_float(getattr(forecast, "avg_daily", 0.0)), 0.0)
            series = list(getattr(forecast, "forecast", []) or [])
            if series:
                period_total = sum(float(row.get("expected_units", 0.0)) for row in series)
                final_period = int(round(max(period_total, 0.0)))
            else:
                period_total = final_daily * horizon
                final_period = int(round(max(period_total, 0.0)))
            trend_hint = _as_float(getattr(forecast, "trend_hint", 0.0), 0.0)
            seasonality_hint = _as_float(getattr(forecast, "seasonality_hint", 0.0), 0.0)

        loc["demand_forecast"] = final_period
        diagnostics.append(
            {
                "location_id": loc_id,
                "sales_base_daily": round(final_daily, 2),
                "sales_trend_daily": round(trend_hint, 2),
                "seasonal_weekly_delta": round(seasonality_hint, 2),
                "weather_daily_impact": 0.0,
                "social_daily_impact": 0.0,
                "final_daily_forecast": round(final_daily, 2),
                "final_period_forecast": final_period,
            }
        )

    allocation_result = allocation.optimize_allocation(product_id, inbound, final_locations)

    return {
        "product_id": product_id,
        "horizon": horizon,
        "allocation_mode": "deterministic",
        "specialist_outputs": diagnostics,
        "allocations": allocation_result["allocations"],
        "inbound_remaining": allocation_result["inbound_remaining"],
        "estimated_total_cost": allocation_result["estimated_total_cost"],
        "fill_rate": allocation_result["fill_rate"],
    }
