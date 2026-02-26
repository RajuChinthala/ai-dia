"""
Sample domain objects and helper functions used by the API and notebooks.
The sample data mirrors the entities listed in the Dynamic-Allocation doc.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import List, Dict


@dataclass
class Product:
    id: str
    name: str


@dataclass
class Location:
    location_id: int
    location_name: str
    inventory_level: int
    demand_forecast: int
    capacity: int
    safety_stock: int
    shipping_cost: float
    service_level: float


def sample_product() -> Product:
    return Product(id="PROD-101", name="Running Shoes")


def sample_locations() -> List[Location]:
    return [
        Location(
            location_id=1001,
            location_name="New York DC",
            inventory_level=150,
            demand_forecast=250,
            capacity=450,
            safety_stock=60,
            shipping_cost=3.0,
            service_level=0.95,
        ),
        Location(
            location_id=1002,
            location_name="Los Angeles Store",
            inventory_level=280,
            demand_forecast=180,
            capacity=400,
            safety_stock=50,
            shipping_cost=4.5,
            service_level=0.9,
        ),
        Location(
            location_id=1003,
            location_name="Chicago Store",
            inventory_level=120,
            demand_forecast=220,
            capacity=380,
            safety_stock=55,
            shipping_cost=2.5,
            service_level=0.92,
        ),
    ]


def sample_sales_history(days: int = 30) -> List[Dict]:
    """Synthetic sales + signals for the forecast demo."""
    start = date.today() - timedelta(days=days)
    prod = sample_product()
    location_ids = [s.location_id for s in sample_locations()]
    history: List[Dict] = []
    for idx in range(days):
        dt = start + timedelta(days=idx)
        for loc_id in location_ids:
            base = 40 + (idx % 7) * 3
            seasonal = 6 if dt.weekday() in (4, 5) else 0
            social_signal = 0.1 * (idx % 5)
            weather_score = 0.05 * (idx % 3)
            units = int(base + seasonal + social_signal * 5 - weather_score * 2)
            history.append(
                {
                    "date": dt.isoformat(),
                    "product_id": prod.id,
                    "location_id": loc_id,
                    "units": units,
                    "social_signal": round(social_signal, 2),
                    "weather_score": round(weather_score, 2),
                    "event_score": 0.15 if idx % 10 == 0 else 0,
                }
            )
    return history


def inbound_inventory() -> Dict[str, int]:
    """Units arriving from DC or vendors for the sample product."""
    return {"PROD-101": 500}
