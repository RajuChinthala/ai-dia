from __future__ import annotations

import json
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes import allocation, forecast, health
from . import allocation as alloc_engine, forecasting, sample_data


app = FastAPI(
    title="Dynamic Inventory Allocation (Prototype)",
    description="Demand forecasting + allocation service seeded with the shared notebook examples.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(forecast.router)
app.include_router(allocation.router)


if __name__ == "__main__":
    # Local smoke test: run forecast + allocation with sample data
    prod = sample_data.sample_product()
    history = sample_data.sample_sales_history()
    forecasts = forecasting.forecast_next_period(history, prod.id, horizon=7)
    inbound = sample_data.inbound_inventory()[prod.id]
    locations = [s.__dict__.copy() for s in sample_data.sample_locations()]
    for loc in locations:
        match = next((f for f in forecasts if f.location_id == loc["location_id"]), None)
        loc["demand_forecast"] = int(match.avg_daily * 7) if match else loc["demand_forecast"]
    plan = alloc_engine.optimize_allocation(prod.id, inbound, locations)
    print("Sample forecast:", json.dumps([forecast.serialize_forecast(f) for f in forecasts], indent=2))
    print("Allocation plan:", json.dumps(plan, indent=2))
