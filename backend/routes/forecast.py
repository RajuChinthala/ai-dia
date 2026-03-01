from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .. import forecasting, sample_data, schemas, notebook_runner
from ..helpers import build_history_and_forecast_from_apis

router = APIRouter()


@router.get("/sample/forecast", response_model=schemas.ForecastResponse)
def sample_forecast(horizon: int = 7):
    prod = sample_data.sample_product()
    history = sample_data.sample_sales_history()
    results = forecasting.forecast_next_period(history, product_id=prod.id, horizon=horizon)
    return {"forecasts": [serialize_forecast(r) for r in results]}


@router.post("/forecast", response_model=schemas.ForecastResponse)
def forecast(req: schemas.ForecastCSVRequest):
    """
    Forecast endpoint backed by the notebook output CSV.
    """
    try:
        results = forecasting.load_csv_forecasts(
            req.csv_path, req.product_id, pred_column=req.pred_column, horizon=req.horizon
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load forecasts: {exc}") from exc
    return {"forecasts": [serialize_forecast(r) for r in results]}


@router.post("/forecast/api", response_model=schemas.ForecastResponse)
def forecast_from_apis(req: schemas.ForecastFromAPIsRequest):
    """
    Build a merged final dataset from Sales + Weather + Social APIs and run forecasting.
    This is notebook-free and uses the same forecast engine used by pipeline option 1.
    """
    try:
        data = build_history_and_forecast_from_apis(
            product_id=req.product_id,
            location_ids=req.location_ids,
            sales_api_url=req.sales_api_url,
            weather_api_url=req.weather_api_url,
            social_api_url=req.social_api_url,
            horizon=req.horizon,
            api_timeout_sec=req.api_timeout_sec,
            retry_max=req.retry_max,
            retry_backoff_sec=req.retry_backoff_sec,
        )

        history = data["history"]
        if not history:
            raise HTTPException(
                status_code=404,
                detail=(
                    "No merged rows could be generated from source APIs. "
                    "Ensure sales rows include date, product_id, location_id, and units."
                ),
            )
        results = data["forecasts"]
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"API forecast failed: {exc}") from exc

    return {"forecasts": [serialize_forecast(r) for r in results]}


@router.post("/pipeline/notebook_forecast", response_model=schemas.NotebookForecastResponse)
def notebook_forecast(req: schemas.NotebookForecastRequest):
    """
    Execute the forecasting notebook and build a standardized demand forecast sheet.
    """
    try:
        executed_path = notebook_runner.run_notebook(
            req.notebook_path,
            working_dir=req.working_dir,
            output_path=req.output_notebook_path,
            timeout=req.timeout,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ImportError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - notebook failures vary
        raise HTTPException(status_code=500, detail=f"Notebook execution failed: {exc}") from exc

    try:
        summary = forecasting.generate_final_demand_sheet(
            req.predictions_csv_path,
            req.final_sheet_path,
            pred_column=req.pred_column,
            forecast_column=req.forecast_column,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to build final sheet: {exc}") from exc

    return {
        "notebook_path": req.notebook_path,
        "executed_notebook_path": executed_path,
        "predictions_csv_path": req.predictions_csv_path,
        "final_sheet_path": req.final_sheet_path,
        "forecast_column": req.forecast_column,
        "summary": summary,
    }


def serialize_forecast(result: forecasting.ForecastResult):
    return {
        "product_id": result.product_id,
        "location_id": result.location_id,
        "horizon": result.horizon,
        "avg_daily": result.avg_daily,
        "trend_hint": result.trend_hint,
        "seasonality_hint": result.seasonality_hint,
        "forecast": result.forecast,
    }
