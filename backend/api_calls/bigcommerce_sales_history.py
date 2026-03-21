from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Dict, List, Optional

import requests

from .bigcommerce_inventory import (
    BigCommerceConfig,
    _require_credentials,
    _to_int,
    get_bigcommerce_config,
)


@dataclass
class SalesHistoryFetchResult:
    rows: List[Dict]
    orders_processed: int
    orders_total: int
    notes: List[str]


def _headers(cfg: BigCommerceConfig) -> Dict[str, str]:
    return {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-Auth-Token": cfg.access_token,
    }


def _request_json(
    *,
    cfg: BigCommerceConfig,
    path: str,
    params: Optional[Dict] = None,
    timeout_sec: int = 20,
    retry_max: int = 3,
    retry_backoff_sec: float = 0.5,
) -> Dict:
    url = f"{cfg.api_base}/stores/{cfg.store_hash}{path}"
    last_error = ""

    for attempt in range(retry_max + 1):
        try:
            response = requests.get(url, headers=_headers(cfg), params=params, timeout=timeout_sec)
            if response.status_code == 429 and attempt < retry_max:
                time.sleep(retry_backoff_sec * (2 ** attempt))
                continue
            if 500 <= response.status_code < 600 and attempt < retry_max:
                time.sleep(retry_backoff_sec * (2 ** attempt))
                continue
            response.raise_for_status()
            if response.status_code == 204:
                return {"data": []}
            raw_text = (response.text or "").strip()
            if not raw_text:
                return {"data": []}
            payload = json.loads(raw_text)
            if isinstance(payload, dict):
                return payload
            if isinstance(payload, list):
                return {"data": payload}
            return {"data": []}
        except Exception as exc:  # pragma: no cover - network/provider variance
            last_error = str(exc)
            if attempt >= retry_max:
                break
            time.sleep(retry_backoff_sec * (2 ** attempt))

    raise ValueError(f"BigCommerce request failed for {path}. Last error: {last_error}")


def _extract_created_date_iso(value: str) -> Optional[str]:
    if not value:
        return None
    candidates = [value]
    if value.endswith("Z"):
        candidates.append(value[:-1] + "+00:00")
    for raw in candidates:
        try:
            dt = datetime.fromisoformat(raw)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).date().isoformat()
        except Exception:
            continue
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).date().isoformat()
    except Exception:
        return None


def _to_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_csv_int(raw: str | None) -> List[int]:
    if not raw:
        return []
    values: List[int] = []
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        try:
            number = int(token)
        except ValueError:
            continue
        if number > 0:
            values.append(number)
    return values


def _fetch_inventory_location_ids(
    *,
    cfg: BigCommerceConfig,
    timeout_sec: int,
    retry_max: int,
    retry_backoff_sec: float,
    max_pages: int,
) -> List[int]:
    page = 1
    ids: List[int] = []

    while page <= max_pages:
        payload = _request_json(
            cfg=cfg,
            path="/v3/inventory/locations",
            params={"limit": 250, "page": page},
            timeout_sec=timeout_sec,
            retry_max=retry_max,
            retry_backoff_sec=retry_backoff_sec,
        )
        rows = payload.get("data") if isinstance(payload, dict) else []
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict):
                continue
            loc_id = _to_int(row.get("id"), -1)
            if loc_id > 0:
                ids.append(loc_id)

        meta = payload.get("meta", {}) if isinstance(payload, dict) else {}
        pagination = meta.get("pagination", {}) if isinstance(meta, dict) else {}
        total_pages = _to_int(pagination.get("total_pages"), page)
        if page >= max(total_pages, 1):
            break
        page += 1

    return sorted(set(ids))


def _extract_order_product_id(line_item: Dict) -> int:
    for key in ("order_product_id", "id", "product_id"):
        value = _to_int(line_item.get(key), 0)
        if value > 0:
            return value
    return 0


def _extract_location_id(consignment: Dict) -> int:
    candidates = [
        consignment.get("location_id"),
        (consignment.get("pickup_method") or {}).get("location_id") if isinstance(consignment.get("pickup_method"), dict) else None,
        (consignment.get("pickup_option") or {}).get("location_id") if isinstance(consignment.get("pickup_option"), dict) else None,
    ]
    for candidate in candidates:
        loc_id = _to_int(candidate, 0)
        if loc_id > 0:
            return loc_id
    return 0


def _fetch_order_products(
    *,
    cfg: BigCommerceConfig,
    order_id: int,
    timeout_sec: int,
    retry_max: int,
    retry_backoff_sec: float,
) -> List[Dict]:
    payload = _request_json(
        cfg=cfg,
        path=f"/v2/orders/{order_id}/products",
        timeout_sec=timeout_sec,
        retry_max=retry_max,
        retry_backoff_sec=retry_backoff_sec,
    )
    rows = payload.get("data") if isinstance(payload, dict) else []
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _fetch_order_consignments(
    *,
    cfg: BigCommerceConfig,
    order_id: int,
    timeout_sec: int,
    retry_max: int,
    retry_backoff_sec: float,
) -> List[Dict]:
    payload = _request_json(
        cfg=cfg,
        path=f"/v2/orders/{order_id}/consignments",
        timeout_sec=timeout_sec,
        retry_max=retry_max,
        retry_backoff_sec=retry_backoff_sec,
    )
    rows = payload.get("data") if isinstance(payload, dict) else []
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _build_order_product_to_location(consignments: List[Dict]) -> Dict[int, int]:
    mapping: Dict[int, int] = {}
    for consignment in consignments:
        if not isinstance(consignment, dict):
            continue
        loc_id = _extract_location_id(consignment)
        line_items = consignment.get("line_items")
        if not isinstance(line_items, list):
            continue
        for item in line_items:
            if not isinstance(item, dict):
                continue
            order_product_id = _extract_order_product_id(item)
            if order_product_id > 0 and loc_id > 0:
                mapping[order_product_id] = loc_id
    return mapping


def fetch_sales_history(
    *,
    product_ids_csv: str | None = None,
    location_ids_csv: str | None = None,
    min_date_created: str | None = None,
    max_date_created: str | None = None,
    status_id: int | None = 10,
    timeout_sec: int = 20,
    retry_max: int = 3,
    retry_backoff_sec: float = 0.5,
    max_pages: int = 20,
    per_page: int = 250,
) -> SalesHistoryFetchResult:
    cfg = get_bigcommerce_config()
    _require_credentials(cfg)

    product_filter = set(_parse_csv_int(product_ids_csv))
    location_filter = set(_parse_csv_int(location_ids_csv))

    inventory_location_ids = _fetch_inventory_location_ids(
        cfg=cfg,
        timeout_sec=timeout_sec,
        retry_max=retry_max,
        retry_backoff_sec=retry_backoff_sec,
        max_pages=max_pages,
    )
    default_location_id = next(iter(sorted(location_filter)), None)
    if default_location_id is None:
        default_location_id = inventory_location_ids[0] if inventory_location_ids else 0

    notes: List[str] = []
    if default_location_id <= 0:
        notes.append("No inventory location found; sales rows will use location_id=0 when unresolved.")

    rows_by_key: Dict[tuple[str, int, int], float] = {}
    page = 1
    orders_total = 0
    orders_processed = 0

    while page <= max_pages:
        params: Dict[str, str | int] = {"page": page, "limit": max(1, min(per_page, 250))}
        if min_date_created:
            params["min_date_created"] = min_date_created
        if max_date_created:
            params["max_date_created"] = max_date_created
        if status_id is not None and status_id >= 0:
            params["status_id"] = int(status_id)

        payload = _request_json(
            cfg=cfg,
            path="/v2/orders",
            params=params,
            timeout_sec=timeout_sec,
            retry_max=retry_max,
            retry_backoff_sec=retry_backoff_sec,
        )
        orders = payload.get("data") if isinstance(payload, dict) else []
        order_rows = [row for row in orders if isinstance(row, dict)] if isinstance(orders, list) else []
        if not order_rows:
            break

        orders_total += len(order_rows)
        for order in order_rows:
            order_id = _to_int(order.get("id"), 0)
            date_value = _extract_created_date_iso(str(order.get("date_created") or ""))
            if order_id <= 0 or not date_value:
                continue

            products = _fetch_order_products(
                cfg=cfg,
                order_id=order_id,
                timeout_sec=timeout_sec,
                retry_max=retry_max,
                retry_backoff_sec=retry_backoff_sec,
            )
            try:
                consignments = _fetch_order_consignments(
                    cfg=cfg,
                    order_id=order_id,
                    timeout_sec=timeout_sec,
                    retry_max=retry_max,
                    retry_backoff_sec=retry_backoff_sec,
                )
            except Exception:
                consignments = []

            item_location_map = _build_order_product_to_location(consignments)

            for item in products:
                product_id = _to_int(item.get("product_id"), 0)
                if product_id <= 0:
                    continue
                if product_filter and product_id not in product_filter:
                    continue

                order_product_id = _extract_order_product_id(item)
                location_id = item_location_map.get(order_product_id, default_location_id)
                if location_id <= 0:
                    location_id = 0

                if location_filter and location_id not in location_filter:
                    continue

                units = _to_float(item.get("quantity"), 0.0)
                if units <= 0:
                    continue

                key = (date_value, product_id, location_id)
                rows_by_key[key] = rows_by_key.get(key, 0.0) + units

            orders_processed += 1

        if len(order_rows) < params["limit"]:
            break
        page += 1

    output_rows = [
        {
            "date": date,
            "product_id": str(product_id),
            "location_id": int(location_id),
            "units": float(units),
        }
        for (date, product_id, location_id), units in rows_by_key.items()
    ]
    output_rows.sort(key=lambda x: (x["date"], int(x["product_id"]), int(x["location_id"])))

    if output_rows and any(int(row["location_id"]) == 0 for row in output_rows):
        notes.append("Some rows used fallback location_id=0 because no consignment-location match was available.")

    return SalesHistoryFetchResult(
        rows=output_rows,
        orders_processed=orders_processed,
        orders_total=orders_total,
        notes=notes,
    )