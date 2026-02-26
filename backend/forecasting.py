"""
Lightweight forecasting utilities for the allocation prototype.
The implementation intentionally uses standard library math so it can run
even when scientific packages are unavailable in the sandbox.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Dict, List, Optional
from pathlib import Path

try:  # Optional convenience when pandas is available
    import pandas as pd  # type: ignore
except Exception:  # pragma: no cover - pandas not required for sample run
    pd = None  # type: ignore


@dataclass
class ForecastResult:
    product_id: str
    location_id: int
    horizon: int
    forecast: List[Dict]
    avg_daily: float
    seasonality_hint: Optional[float] = None
    trend_hint: Optional[float] = None


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


def forecast_next_period(
    history: List[Dict], product_id: str, horizon: int = 7
) -> List[ForecastResult]:
    """
    Compute naive forecasts per store using moving averages with tiny trend/seasonal bumps.
    Returns one ForecastResult per store.
    """
    grouped: Dict[int, List[float]] = defaultdict(list)
    social: Dict[int, List[float]] = defaultdict(list)
    weather: Dict[int, List[float]] = defaultdict(list)

    for row in history:
        if row.get("product_id") != product_id:
            continue
        location_id = int(row["location_id"])
        grouped[location_id].append(float(row.get("units", 0)))
        social[location_id].append(float(row.get("social_signal", 0.0)))
        weather[location_id].append(float(row.get("weather_score", 0.0)))

    results: List[ForecastResult] = []
    for location_id, values in grouped.items():
        base = _moving_average(values, window=7)
        trend = _trend(values)
        seasonal = _seasonality(values, period=7)
        social_lift = _moving_average(social[location_id], window=7) * 2
        weather_impact = _moving_average(weather[location_id], window=7) * -1.5

        daily = base + trend + seasonal + social_lift + weather_impact
        daily = max(daily, 0.0)
        forecast = []
        for i in range(1, horizon + 1):
            bump = trend * i
            forecast.append(
                {
                    "date": (date.today() + timedelta(days=i)).isoformat(),
                    "expected_units": round(max(daily + bump, 0.0), 2),
                }
            )

        results.append(
            ForecastResult(
                product_id=product_id,
                location_id=location_id,
                horizon=horizon,
                forecast=forecast,
                avg_daily=round(daily, 2),
                seasonality_hint=round(seasonal, 2),
                trend_hint=round(trend, 3),
            )
        )

    return results


def to_dataframe(results: List[ForecastResult]):
    """Convenience conversion for notebooks when pandas is present."""
    if pd is None:
        raise ImportError("pandas is not installed in this environment.")
    records = []
    for res in results:
        for row in res.forecast:
            records.append(
                {
                    "product_id": res.product_id,
                    "location_id": res.location_id,
                    "date": row["date"],
                    "expected_units": row["expected_units"],
                }
            )
    return pd.DataFrame(records)


def load_csv_forecasts(
    csv_path: str,
    product_id: str,
    pred_column: str = "pred_ensemble",
    horizon: int = 7,
) -> List[ForecastResult]:
    """
    Load precomputed forecasts from validation_preds.csv (exported by notebook).
    Expects columns: product_id, location_id, date, target, pred_lgb, pred_prophet, pred_ensemble.
    """
    if pd is None:
        raise ImportError("pandas is not installed; required for CSV forecasts.")
    df = pd.read_csv(csv_path)
    # accept numeric or string product ids
    df["product_id"] = df["product_id"].astype(str)
    df = df[df["product_id"] == str(product_id)]
    if df.empty:
        return []
    if pred_column not in df.columns:
        raise ValueError(f"Column {pred_column} not in CSV")

    results: List[ForecastResult] = []
    for loc_id, grp in df.groupby("location_id"):
        grp = grp.sort_values("date").head(horizon)
        fcst = []
        for _, row in grp.iterrows():
            fcst.append({"date": row["date"], "expected_units": float(row[pred_column])})
        avg = float(grp[pred_column].mean())
        results.append(
            ForecastResult(
                product_id=str(product_id),
                location_id=int(loc_id),
                horizon=len(fcst),
                forecast=fcst,
                avg_daily=round(avg, 2),
                seasonality_hint=None,
                trend_hint=None,
            )
        )
    return results


def generate_final_demand_sheet(
    source_csv_path: str,
    output_csv_path: str,
    pred_column: str = "pred_ensemble",
    forecast_column: str = "forecast_units",
) -> Dict[str, Optional[float]]:
    """
    Build a simplified demand forecast sheet from the notebook predictions CSV.
    Output columns: product_id, location_id, date, forecast_units (or custom column name).
    """
    if pd is None:
        raise ImportError("pandas is not installed; required for CSV processing.")

    df = pd.read_csv(source_csv_path)
    required = {"product_id", "location_id", "date"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")
    if pred_column not in df.columns:
        raise ValueError(f"Column {pred_column} not in CSV")

    out = df[["product_id", "location_id", "date", pred_column]].copy()
    out.rename(columns={pred_column: forecast_column}, inplace=True)
    out["product_id"] = out["product_id"].astype(str)
    out = out.sort_values(["product_id", "location_id", "date"])

    out_path = Path(output_csv_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(out_path, index=False)

    if out.empty:
        return {
            "rows": 0,
            "products": 0,
            "locations": 0,
            "date_start": None,
            "date_end": None,
        }

    return {
        "rows": int(len(out)),
        "products": int(out["product_id"].nunique()),
        "locations": int(out["location_id"].nunique()),
        "date_start": str(out["date"].min()),
        "date_end": str(out["date"].max()),
    }
