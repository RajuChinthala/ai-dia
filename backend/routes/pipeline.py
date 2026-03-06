from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .. import chroma_memory, llm_pipeline, schemas
from ..api_calls.config import get_source_api_config
from ..helpers import build_history_and_forecast_from_apis

router = APIRouter()


@router.get("/pipeline/memory/health")
def memory_health():
    return chroma_memory.get_memory_health()


@router.post("/pipeline/agent_forecast_allocate", response_model=schemas.AgentPipelineResponse)
def agent_forecast_allocate(req: schemas.AgentPipelineRequest):
    try:
        history_rows = [r.model_dump() for r in req.history]
        if not history_rows:
            source_cfg = get_source_api_config()
            sales_api_url = (req.sales_api_url or source_cfg.sales_api_url).strip()
            weather_api_url = (req.weather_api_url or source_cfg.weather_api_url).strip()
            seasonal_api_url = (req.seasonal_api_url or req.social_api_url or source_cfg.seasonal_api_url).strip()

            if not sales_api_url or not weather_api_url or not seasonal_api_url:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Missing source API URLs. Configure backend/api_calls/config.py or set "
                        "SOURCE_SALES_API_URL, SOURCE_WEATHER_API_URL, SOURCE_SEASONAL_API_URL."
                    ),
                )

            data = build_history_and_forecast_from_apis(
                product_id=req.product_id,
                location_ids=[int(loc.location_id) for loc in req.locations],
                sales_api_url=sales_api_url,
                weather_api_url=weather_api_url,
                seasonal_api_url=seasonal_api_url,
                social_api_url=req.social_api_url,
                horizon=req.horizon,
                api_timeout_sec=req.api_timeout_sec,
                retry_max=req.retry_max,
                retry_backoff_sec=req.retry_backoff_sec,
            )
            history_rows = data["history"]

        if not history_rows:
            raise HTTPException(
                status_code=404,
                detail=(
                    "No merged history rows could be generated from source APIs. "
                    "Check source payload fields (date, product_id, location_id, units) and data freshness."
                ),
            )

        result = llm_pipeline.run_llm_orchestrated_pipeline(
            product_id=req.product_id,
            inbound=req.inbound,
            locations=[s.model_dump() for s in req.locations],
            history=history_rows,
            horizon=req.horizon,
        )
    except Exception as exc:
        if isinstance(exc, HTTPException):
            raise exc
        if isinstance(exc, ValueError):
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        raise HTTPException(status_code=500, detail=f"Agent pipeline failed: {exc}") from exc

    result["variant_id"] = req.variant_id
    return result
