from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class SourceApiConfig:
    sales_api_url: str
    weather_api_url: str
    seasonal_api_url: str


def get_source_api_config() -> SourceApiConfig:
    sales_api_url = os.getenv("SOURCE_SALES_API_URL", "builtin://sales?days=14&products=5&seed=42").strip()
    weather_api_url = os.getenv(
        "SOURCE_WEATHER_API_URL",
        "builtin://weather?city=OHIO&lat=40.1088&lon=-82.9742&days=4",
    ).strip()
    seasonal_api_url = os.getenv(
        "SOURCE_SEASONAL_API_URL",
        "builtin://social?days=14&seed=42",
    ).strip()

    return SourceApiConfig(
        sales_api_url=sales_api_url,
        weather_api_url=weather_api_url,
        seasonal_api_url=seasonal_api_url,
    )
