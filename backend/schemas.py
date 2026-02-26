from __future__ import annotations

from typing import List, Dict, Optional

from pydantic import BaseModel, Field


class ForecastCSVRequest(BaseModel):
    product_id: str = Field(..., example="PROD-101")
    csv_path: str = Field(
        "notebooks/final_demand_forecast.csv", description="Path to final demand forecast sheet"
    )
    pred_column: str = Field(
        "forecast_units", description="Forecast column to use from final demand sheet"
    )
    horizon: int = Field(7, ge=1, le=60, description="Number of days to consider from CSV")


class ForecastResponse(BaseModel):
    forecasts: List[Dict]


class LocationInput(BaseModel):
    location_id: int = Field(..., description="BigCommerce location id")
    location_name: Optional[str] = None
    inventory_level: int = Field(..., description="Inventory level at location")
    demand_forecast: int
    capacity: int
    safety_stock: int = 0
    shipping_cost: float = 0.0
    service_level: float = 0.9


class AllocationRequest(BaseModel):
    product_id: str
    variant_id: Optional[int] = Field(None, description="Variant id for ATS updates")
    inbound: int = Field(..., ge=0, description="Units inbound from vendor/DC")
    locations: List[LocationInput]


class AllocationResponse(BaseModel):
    product_id: str
    variant_id: Optional[int] = None
    allocations: List[Dict]
    inbound_remaining: int
    estimated_total_cost: float
    fill_rate: float


class NotebookForecastRequest(BaseModel):
    notebook_path: str = Field(
        "notebooks/demand_forecast_updated.ipynb", description="Notebook to execute"
    )
    working_dir: Optional[str] = Field(
        "notebooks", description="Working directory for notebook execution"
    )
    output_notebook_path: Optional[str] = Field(
        None, description="Optional path to write the executed notebook"
    )
    predictions_csv_path: str = Field(
        "notebooks/validation_preds.csv", description="Notebook output predictions CSV"
    )
    final_sheet_path: str = Field(
        "notebooks/final_demand_forecast.csv",
        description="Standardized demand forecast sheet output path",
    )
    pred_column: str = Field("pred_ensemble", description="Prediction column to use")
    forecast_column: str = Field("forecast_units", description="Output forecast column name")
    timeout: int = Field(1200, ge=60, le=7200, description="Notebook execution timeout (seconds)")


class NotebookForecastResponse(BaseModel):
    notebook_path: str
    executed_notebook_path: Optional[str] = None
    predictions_csv_path: str
    final_sheet_path: str
    forecast_column: str
    summary: Dict
