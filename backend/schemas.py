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


class ForecastFromAPIsRequest(BaseModel):
    product_id: str = Field(..., description="Product/SKU identifier")
    location_ids: List[int] = Field(default_factory=list, description="Optional location filter")
    sales_api_url: str = Field(..., description="Sales history API URL")
    weather_api_url: str = Field(..., description="Weather signal API URL")
    social_api_url: str = Field(..., description="Social trends API URL")
    horizon: int = Field(7, ge=1, le=60, description="Forecast horizon in days")
    api_timeout_sec: int = Field(15, ge=2, le=120)
    retry_max: int = Field(3, ge=0, le=8)
    retry_backoff_sec: float = Field(0.5, ge=0.1, le=30.0)


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


class HistoryRow(BaseModel):
    date: str
    product_id: str
    location_id: int
    units: float = 0.0
    social_signal: float = 0.0
    weather_score: float = 0.0
    event_score: float = 0.0


class AgentPipelineRequest(BaseModel):
    product_id: str
    variant_id: Optional[int] = Field(None, description="Variant id for ATS updates")
    inbound: int = Field(..., ge=0, description="Units inbound from vendor/DC")
    locations: List[LocationInput]
    history: List[HistoryRow] = Field(default_factory=list, description="Optional override history rows")
    horizon: int = Field(7, ge=1, le=60, description="Forecast horizon in days")
    sales_api_url: Optional[str] = Field(None, description="Sales history API endpoint")
    weather_api_url: Optional[str] = Field(None, description="Weather signal API endpoint")
    seasonal_api_url: Optional[str] = Field(None, description="Seasonal/event trend API endpoint")
    social_api_url: Optional[str] = Field(
        None,
        description="Deprecated alias for seasonal_api_url",
    )
    api_timeout_sec: int = Field(15, ge=2, le=120, description="Per-request timeout for source APIs")
    retry_max: int = Field(3, ge=0, le=8, description="Max retries for transient API failures")
    retry_backoff_sec: float = Field(
        0.5,
        ge=0.1,
        le=30.0,
        description="Initial retry backoff in seconds; exponential backoff with jitter-like growth",
    )


class AgentSignals(BaseModel):
    location_id: int
    sales_base_daily: float
    sales_trend_daily: float
    seasonal_weekly_delta: float
    weather_daily_impact: float
    social_daily_impact: float
    final_daily_forecast: float
    final_period_forecast: int


class AgentPipelineResponse(BaseModel):
    product_id: str
    variant_id: Optional[int] = None
    history_source: Optional[str] = None
    horizon: int
    allocation_mode: str
    specialist_outputs: List[AgentSignals]
    allocations: List[Dict]
    inbound_remaining: int
    estimated_total_cost: float
    fill_rate: float
    retrieval_context: Optional[Dict] = None


class BigCommerceProductLocation(BaseModel):
    location_id: int
    location_name: str
    inventory_level: int
    availability: str
    capacity: int
    safety_stock: int
    shipping_cost: float
    service_level: float


class BigCommerceProductWithLocations(BaseModel):
    product_id: int
    variant_id: Optional[int] = None
    sku: str
    product_name: str
    total_inventory_level: int
    locations: List[BigCommerceProductLocation]


class BigCommerceProductsLocationsResponse(BaseModel):
    source: str
    product_count: int
    products: List[BigCommerceProductWithLocations]


class BigCommerceAllocationPayloadResponse(BaseModel):
    source: str
    selected_product: BigCommerceProductWithLocations
    allocation_payload: AllocationRequest


class BigCommerceSalesHistoryRow(BaseModel):
    date: str
    product_id: str
    location_id: int
    units: float


class BigCommerceSalesHistoryResponse(BaseModel):
    source: str
    row_count: int
    orders_processed: int
    orders_total: int
    notes: List[str] = Field(default_factory=list)
    rows: List[BigCommerceSalesHistoryRow]
