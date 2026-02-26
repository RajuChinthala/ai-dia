from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .. import allocation, forecasting, sample_data, schemas, llm_allocation

router = APIRouter()


@router.get("/sample/allocate", response_model=schemas.AllocationResponse)
def sample_allocate():
    prod = sample_data.sample_product()
    inbound = sample_data.inbound_inventory()[prod.id]
    locations = [s.__dict__.copy() for s in sample_data.sample_locations()]
    forecasts = forecasting.forecast_next_period(sample_data.sample_sales_history(), prod.id, horizon=7)
    by_loc = {f.location_id: f for f in forecasts}
    for loc in locations:
        loc["demand_forecast"] = int(by_loc[loc["location_id"]].avg_daily * 7)
    plan = allocation.optimize_allocation(prod.id, inbound, locations)
    plan["variant_id"] = None
    return plan


@router.post("/allocate", response_model=schemas.AllocationResponse)
def allocate(req: schemas.AllocationRequest):
    locations = [s.dict() for s in req.locations]
    plan = allocation.optimize_allocation(req.product_id, req.inbound, locations)
    plan["variant_id"] = req.variant_id
    return plan


@router.post("/llm/allocation", response_model=schemas.AllocationResponse)
def allocate_with_llm(req: schemas.AllocationRequest):
    locations = [s.dict() for s in req.locations]
    try:
        plan = llm_allocation.llm_optimize_allocation(req.product_id, req.inbound, locations)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"LLM allocation failed: {exc}") from exc
    plan["variant_id"] = req.variant_id
    return plan
