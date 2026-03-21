from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .. import chroma_memory, llm_pipeline, schemas
from ..api_calls.bigcommerce_inventory import fetch_products_with_locations
from ..api_calls.bigcommerce_sales_history import fetch_sales_history
from ..api_calls.config import get_source_api_config
from ..helpers import build_history_and_forecast_from_apis

router = APIRouter()


@router.get("/pipeline/memory/health")
def memory_health():
    return chroma_memory.get_memory_health()


@router.get("/pipeline/bigcommerce/products_locations")
@router.get("/pipeline/bigcommerce/locations_products")
def bigcommerce_locations_products(
    product_ids: str | None = None,
    location_ids: str | None = None,
    timeout_sec: int = 20,
    retry_max: int = 3,
    retry_backoff_sec: float = 0.5,
    max_pages: int = 25,
    products_per_location: int = 50,
    include_csv_data: bool = True,
    location_products_csv_path: str | None = None,
) -> schemas.BigCommerceProductsLocationsResponse:
    def _parse_csv_int(raw: str | None) -> list[int]:
        if not raw:
            return []
        values: list[int] = []
        for token in raw.split(","):
            token = token.strip()
            if not token:
                continue
            try:
                values.append(int(token))
            except ValueError:
                continue
        return values

    try:
        products = fetch_products_with_locations(
            product_ids=_parse_csv_int(product_ids),
            location_ids=_parse_csv_int(location_ids),
            timeout_sec=max(5, min(timeout_sec, 120)),
            retry_max=max(0, min(retry_max, 8)),
            retry_backoff_sec=max(0.1, min(retry_backoff_sec, 10.0)),
            max_pages=max(1, min(max_pages, 100)),
            products_per_location=max(0, min(products_per_location, 20000)),
            include_csv_data=bool(include_csv_data),
            location_products_csv_path=(location_products_csv_path or "").strip() or None,
        )
        return {
            "source": "bigcommerce+csv" if include_csv_data else "bigcommerce",
            "product_count": len(products),
            "products": products,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to load BigCommerce inventory: {exc}") from exc


@router.get("/pipeline/bigcommerce/allocation_payload", response_model=schemas.BigCommerceAllocationPayloadResponse)
def bigcommerce_allocation_payload(
    product_id: int | None = None,
    variant_id: int | None = None,
    product_ids: str | None = None,
    location_ids: str | None = None,
    inbound: int = 0,
    timeout_sec: int = 20,
    retry_max: int = 3,
    retry_backoff_sec: float = 0.5,
    max_pages: int = 25,
    products_per_location: int = 50,
    include_csv_data: bool = True,
    location_products_csv_path: str | None = None,
):
    def _parse_csv_int(raw: str | None) -> list[int]:
        if not raw:
            return []
        values: list[int] = []
        for token in raw.split(","):
            token = token.strip()
            if not token:
                continue
            try:
                values.append(int(token))
            except ValueError:
                continue
        return values

    try:
        products = fetch_products_with_locations(
            product_ids=_parse_csv_int(product_ids),
            location_ids=_parse_csv_int(location_ids),
            timeout_sec=max(5, min(timeout_sec, 120)),
            retry_max=max(0, min(retry_max, 8)),
            retry_backoff_sec=max(0.1, min(retry_backoff_sec, 10.0)),
            max_pages=max(1, min(max_pages, 100)),
            products_per_location=max(0, min(products_per_location, 20000)),
            include_csv_data=bool(include_csv_data),
            location_products_csv_path=(location_products_csv_path or "").strip() or None,
        )

        if not products:
            raise HTTPException(status_code=404, detail="No BigCommerce products found for the provided filters.")

        selected = None
        for row in products:
            row_pid = int(row.get("product_id", 0))
            row_vid = row.get("variant_id")
            if variant_id is not None and row_vid is not None and int(row_vid) == int(variant_id):
                selected = row
                break
            if product_id is not None and row_pid == int(product_id):
                selected = row
                break
        if selected is None:
            selected = products[0]

        selected_product_id = str(int(selected.get("product_id", 0)))
        selected_variant_id_raw = selected.get("variant_id")
        selected_variant_id = int(selected_variant_id_raw) if selected_variant_id_raw is not None else None

        allocation_locations = [
            {
                "location_id": int(loc.get("location_id", 0)),
                "location_name": str(loc.get("location_name") or ""),
                "inventory_level": int(loc.get("inventory_level", 0)),
                "demand_forecast": 0,
                "capacity": int(loc.get("capacity", 500)),
                "safety_stock": int(loc.get("safety_stock", 50)),
                "shipping_cost": float(loc.get("shipping_cost", 3.0)),
                "service_level": float(loc.get("service_level", 0.9)),
            }
            for loc in (selected.get("locations") or [])
            if int(loc.get("location_id", 0)) > 0
        ]

        if not allocation_locations:
            raise HTTPException(
                status_code=404,
                detail=f"Product {selected_product_id} has no location inventory rows.",
            )

        return {
            "source": "bigcommerce+csv" if include_csv_data else "bigcommerce",
            "selected_product": selected,
            "allocation_payload": {
                "product_id": selected_product_id,
                "variant_id": selected_variant_id,
                "inbound": max(int(inbound), 0),
                "locations": allocation_locations,
            },
        }
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to build BigCommerce allocation payload: {exc}") from exc


@router.get("/pipeline/bigcommerce/sales_history", response_model=schemas.BigCommerceSalesHistoryResponse)
def bigcommerce_sales_history(
    product_ids: str | None = None,
    location_ids: str | None = None,
    min_date_created: str | None = None,
    max_date_created: str | None = None,
    status_id: int | None = 10,
    timeout_sec: int = 20,
    retry_max: int = 3,
    retry_backoff_sec: float = 0.5,
    max_pages: int = 20,
    per_page: int = 250,
) -> schemas.BigCommerceSalesHistoryResponse:
    try:
        result = fetch_sales_history(
            product_ids_csv=product_ids,
            location_ids_csv=location_ids,
            min_date_created=min_date_created,
            max_date_created=max_date_created,
            status_id=status_id,
            timeout_sec=max(5, min(timeout_sec, 120)),
            retry_max=max(0, min(retry_max, 8)),
            retry_backoff_sec=max(0.1, min(retry_backoff_sec, 10.0)),
            max_pages=max(1, min(max_pages, 100)),
            per_page=max(1, min(per_page, 250)),
        )
        return {
            "source": "bigcommerce",
            "row_count": len(result.rows),
            "orders_processed": result.orders_processed,
            "orders_total": result.orders_total,
            "notes": result.notes,
            "rows": result.rows,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to load BigCommerce sales history: {exc}") from exc


@router.post("/pipeline/agent_forecast_allocate", response_model=schemas.AgentPipelineResponse)
def agent_forecast_allocate(req: schemas.AgentPipelineRequest):
    try:
        history_rows = [r.model_dump() for r in req.history]
        history_source = "provided" if history_rows else ""
        if not history_rows:
            # Prefer BigCommerce order history when product id is numeric and credentials are configured.
            # If BigCommerce yields no rows, fall back to the existing source API merge flow.
            numeric_product_id: int | None = None
            try:
                parsed_product_id = int(str(req.product_id).strip())
                if parsed_product_id > 0:
                    numeric_product_id = parsed_product_id
            except Exception:
                numeric_product_id = None

            if numeric_product_id is not None:
                try:
                    location_ids_csv = ",".join(
                        str(int(loc.location_id))
                        for loc in req.locations
                        if int(loc.location_id) > 0
                    )
                    bc_history = fetch_sales_history(
                        product_ids_csv=str(numeric_product_id),
                        location_ids_csv=location_ids_csv or None,
                        status_id=10,
                        timeout_sec=max(5, min(req.api_timeout_sec, 120)),
                        retry_max=max(0, min(req.retry_max, 8)),
                        retry_backoff_sec=max(0.1, min(req.retry_backoff_sec, 10.0)),
                        max_pages=20,
                        per_page=250,
                    )
                    if bc_history.rows:
                        history_rows = [
                            {
                                "date": row.get("date"),
                                "product_id": str(row.get("product_id")),
                                "location_id": int(row.get("location_id", 0)),
                                "units": float(row.get("units", 0.0)),
                                "social_signal": 0.0,
                                "weather_score": 0.0,
                                "event_score": 0.0,
                            }
                            for row in bc_history.rows
                            if row.get("date")
                        ]
                        if history_rows:
                            history_source = "bigcommerce"
                except Exception:
                    # Swallow provider-specific BigCommerce failures and continue with default fallback sources.
                    history_rows = []

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
            if history_rows:
                history_source = "default"

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
    result["history_source"] = history_source or "default"
    return result
