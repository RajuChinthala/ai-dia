from __future__ import annotations

import csv
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import requests


@dataclass
class BigCommerceConfig:
    store_hash: str
    access_token: str
    api_base: str


def get_bigcommerce_config() -> BigCommerceConfig:
    store_hash = (os.getenv("BIGCOMMERCE_STORE_HASH") or "").strip()
    access_token = (os.getenv("BIGCOMMERCE_ACCESS_TOKEN") or "").strip()
    api_base = (os.getenv("BIGCOMMERCE_API_BASE") or "https://api.bigcommerce.com").strip().rstrip("/")
    return BigCommerceConfig(store_hash=store_hash, access_token=access_token, api_base=api_base)


def _require_credentials(cfg: BigCommerceConfig) -> None:
    if not cfg.store_hash or not cfg.access_token:
        raise ValueError(
            "Missing BigCommerce credentials. Set BIGCOMMERCE_STORE_HASH and BIGCOMMERCE_ACCESS_TOKEN."
        )


def _headers(cfg: BigCommerceConfig) -> Dict[str, str]:
    return {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-Auth-Token": cfg.access_token,
    }


def _to_int(value, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _to_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


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
            payload = response.json()
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


def _paginate_data(
    *,
    cfg: BigCommerceConfig,
    path: str,
    params: Optional[Dict] = None,
    page_limit: int = 25,
    timeout_sec: int = 20,
    retry_max: int = 3,
    retry_backoff_sec: float = 0.5,
) -> List[Dict]:
    merged: List[Dict] = []
    page = 1

    while page <= page_limit:
        current_params = {**(params or {}), "page": page}
        payload = _request_json(
            cfg=cfg,
            path=path,
            params=current_params,
            timeout_sec=timeout_sec,
            retry_max=retry_max,
            retry_backoff_sec=retry_backoff_sec,
        )
        rows = payload.get("data") if isinstance(payload, dict) else []
        if isinstance(rows, list):
            merged.extend([row for row in rows if isinstance(row, dict)])

        meta = payload.get("meta", {}) if isinstance(payload, dict) else {}
        pagination = meta.get("pagination", {}) if isinstance(meta, dict) else {}
        total_pages = _to_int(pagination.get("total_pages"), page)
        if page >= max(total_pages, 1):
            break
        page += 1

    return merged


def _extract_inventory_row(row: Dict) -> Dict:
    location_id = _to_int(
        row.get("location_id")
        or row.get("locationId")
        or row.get("location", {}).get("id")
        or row.get("location", {}).get("location_id"),
        -1,
    )
    product_id = _to_int(
        row.get("product_id") or row.get("productId") or row.get("item", {}).get("product_id"),
        -1,
    )
    variant_id = _to_int(
        row.get("variant_id") or row.get("variantId") or row.get("item", {}).get("variant_id"),
        0,
    )
    sku = str(
        row.get("sku")
        or row.get("item", {}).get("sku")
        or row.get("variant", {}).get("sku")
        or ""
    ).strip()

    quantity = _to_float(
        row.get("available_to_sell")
        or row.get("available_to_sell_quantity")
        or row.get("available")
        or row.get("quantity")
        or row.get("on_hand")
        or row.get("stock")
        or 0.0,
        0.0,
    )

    return {
        "location_id": location_id,
        "product_id": product_id,
        "variant_id": variant_id if variant_id > 0 else None,
        "sku": sku,
        "inventory_level": max(int(round(quantity)), 0),
    }


def _normalize_inventory_rows(rows: List[Dict]) -> List[Dict]:
    """Normalize inventory rows across BigCommerce response variants.

    BigCommerce `v3/inventory/items` can return either:
    - flat rows with top-level location/product fields
    - nested rows with `identity` and `locations[]`
    """
    normalized: List[Dict] = []

    for row in rows:
        if not isinstance(row, dict):
            continue

        identity = row.get("identity") if isinstance(row.get("identity"), dict) else None
        nested_locations = row.get("locations") if isinstance(row.get("locations"), list) else None

        if identity and nested_locations is not None:
            product_id = _to_int(identity.get("product_id") or row.get("product_id"), -1)
            variant_id_val = _to_int(identity.get("variant_id") or row.get("variant_id"), 0)
            variant_id = variant_id_val if variant_id_val > 0 else None
            sku = str(identity.get("sku") or row.get("sku") or "").strip()

            for loc in nested_locations:
                if not isinstance(loc, dict):
                    continue
                normalized.append(
                    {
                        "location_id": _to_int(loc.get("location_id"), -1),
                        "product_id": product_id,
                        "variant_id": variant_id,
                        "sku": sku,
                        "inventory_level": max(
                            _to_int(
                                loc.get("available_to_sell")
                                or loc.get("available_to_sell_quantity")
                                or loc.get("total_inventory_onhand")
                                or 0,
                                0,
                            ),
                            0,
                        ),
                    }
                )
            continue

        normalized.append(_extract_inventory_row(row))

    return normalized


def _availability_label(quantity: int) -> str:
    if quantity <= 0:
        return "out_of_stock"
    if quantity <= 10:
        return "low_stock"
    return "available"


def _chunk(values: Iterable[int], size: int) -> Iterable[List[int]]:
    buf: List[int] = []
    for value in values:
        buf.append(value)
        if len(buf) >= size:
            yield buf
            buf = []
    if buf:
        yield buf


def _fetch_product_names(
    *,
    cfg: BigCommerceConfig,
    product_ids: List[int],
    timeout_sec: int,
    retry_max: int,
    retry_backoff_sec: float,
) -> Dict[int, str]:
    names: Dict[int, str] = {}
    clean_ids = sorted({pid for pid in product_ids if pid > 0})
    if not clean_ids:
        return names

    for group in _chunk(clean_ids, size=50):
        payload = _request_json(
            cfg=cfg,
            path="/v3/catalog/products",
            params={"id:in": ",".join(str(x) for x in group), "limit": len(group)},
            timeout_sec=timeout_sec,
            retry_max=retry_max,
            retry_backoff_sec=retry_backoff_sec,
        )
        for row in payload.get("data", []):
            if not isinstance(row, dict):
                continue
            product_id = _to_int(row.get("id"), -1)
            if product_id > 0:
                names[product_id] = str(row.get("name") or f"Product {product_id}")

    return names


def _as_optional_int(value) -> int | None:
    parsed = _to_int(value, 0)
    return parsed if parsed > 0 else None


def _resolve_location_products_csv_path() -> Path:
    configured = (os.getenv("LOCATION_PRODUCTS_CSV_PATH") or "").strip()
    if configured:
        return Path(configured)
    return Path("notebooks") / "location_products.csv"


def _read_location_products_csv_rows(csv_path: Path) -> List[Dict]:
    if not csv_path.exists() or not csv_path.is_file():
        return []

    rows: List[Dict] = []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            if not isinstance(row, dict):
                continue
            product_id = _to_int(row.get("product_id"), -1)
            location_id = _to_int(row.get("location_id"), -1)
            if product_id <= 0 or location_id <= 0:
                continue

            qty = max(_to_int(row.get("inventory_level"), 0), 0)
            variant_id = _as_optional_int(row.get("variant_id"))
            availability = str(row.get("availability") or "").strip() or _availability_label(qty)

            rows.append(
                {
                    "product_id": product_id,
                    "variant_id": variant_id,
                    "sku": str(row.get("sku") or "").strip(),
                    "product_name": str(row.get("product_name") or f"Product {product_id}"),
                    "location": {
                        "location_id": location_id,
                        "location_name": str(row.get("location_name") or f"Location {location_id}"),
                        "inventory_level": qty,
                        "availability": availability,
                        "capacity": max(_to_int(row.get("capacity"), 500), 0),
                        "safety_stock": max(_to_int(row.get("safety_stock"), 50), 0),
                        "shipping_cost": max(_to_float(row.get("shipping_cost"), 3.0), 0.0),
                        "service_level": max(min(_to_float(row.get("service_level"), 0.9), 1.0), 0.0),
                    },
                }
            )

    return rows


def _merge_csv_products_with_bigcommerce(products: List[Dict], csv_rows: List[Dict]) -> List[Dict]:
    by_product: Dict[tuple[int, int | None], Dict] = {}

    for product in products:
        product_id = _to_int(product.get("product_id"), -1)
        if product_id <= 0:
            continue
        variant_id = _as_optional_int(product.get("variant_id"))
        key = (product_id, variant_id)

        normalized_locations = [
            {
                "location_id": _to_int(loc.get("location_id"), -1),
                "location_name": str(loc.get("location_name") or "").strip() or f"Location {_to_int(loc.get('location_id'), -1)}",
                "inventory_level": max(_to_int(loc.get("inventory_level"), 0), 0),
                "availability": str(loc.get("availability") or "").strip()
                or _availability_label(max(_to_int(loc.get("inventory_level"), 0), 0)),
                "capacity": max(_to_int(loc.get("capacity"), 500), 0),
                "safety_stock": max(_to_int(loc.get("safety_stock"), 50), 0),
                "shipping_cost": max(_to_float(loc.get("shipping_cost"), 3.0), 0.0),
                "service_level": max(min(_to_float(loc.get("service_level"), 0.9), 1.0), 0.0),
            }
            for loc in (product.get("locations") or [])
            if _to_int(loc.get("location_id"), -1) > 0
        ]

        by_product[key] = {
            "product_id": product_id,
            "variant_id": variant_id,
            "sku": str(product.get("sku") or "").strip(),
            "product_name": str(product.get("product_name") or f"Product {product_id}"),
            "locations": normalized_locations,
        }

    for row in csv_rows:
        product_id = _to_int(row.get("product_id"), -1)
        if product_id <= 0:
            continue
        variant_id = _as_optional_int(row.get("variant_id"))
        key = (product_id, variant_id)

        product = by_product.setdefault(
            key,
            {
                "product_id": product_id,
                "variant_id": variant_id,
                "sku": str(row.get("sku") or "").strip(),
                "product_name": str(row.get("product_name") or f"Product {product_id}"),
                "locations": [],
            },
        )

        if not product.get("sku"):
            product["sku"] = str(row.get("sku") or "").strip()
        if not product.get("product_name"):
            product["product_name"] = str(row.get("product_name") or f"Product {product_id}")

        location = row.get("location") if isinstance(row.get("location"), dict) else None
        if not location:
            continue

        loc_id = _to_int(location.get("location_id"), -1)
        if loc_id <= 0:
            continue

        existing = next((loc for loc in product["locations"] if _to_int(loc.get("location_id"), -1) == loc_id), None)
        if existing is None:
            product["locations"].append(location)
        else:
            # Prefer CSV values when the same product+location exists, so local enrichments can override defaults.
            existing.update(location)

    merged = []
    for product in by_product.values():
        locations = sorted(
            [loc for loc in product.get("locations", []) if _to_int(loc.get("location_id"), -1) > 0],
            key=lambda x: _to_int(x.get("location_id"), 0),
        )
        total_inventory = sum(max(_to_int(loc.get("inventory_level"), 0), 0) for loc in locations)
        merged.append(
            {
                "product_id": _to_int(product.get("product_id"), 0),
                "variant_id": _as_optional_int(product.get("variant_id")),
                "sku": str(product.get("sku") or "").strip(),
                "product_name": str(product.get("product_name") or f"Product {_to_int(product.get('product_id'), 0)}"),
                "total_inventory_level": total_inventory,
                "locations": locations,
            }
        )

    merged.sort(key=lambda x: (int(x.get("product_id", 0)), str(x.get("variant_id") or "")))
    return merged


def fetch_products_with_locations(
    *,
    product_ids: Optional[List[int]] = None,
    location_ids: Optional[List[int]] = None,
    timeout_sec: int = 20,
    retry_max: int = 3,
    retry_backoff_sec: float = 0.5,
    max_pages: int = 25,
    products_per_location: int = 50,
    include_csv_data: bool = True,
    location_products_csv_path: Optional[str] = None,
) -> List[Dict]:
    cfg = get_bigcommerce_config()
    _require_credentials(cfg)

    locations = _paginate_data(
        cfg=cfg,
        path="/v3/inventory/locations",
        params={"limit": 250},
        page_limit=max_pages,
        timeout_sec=timeout_sec,
        retry_max=retry_max,
        retry_backoff_sec=retry_backoff_sec,
    )

    inventory_rows = _paginate_data(
        cfg=cfg,
        path="/v3/inventory/items",
        params={"limit": 250},
        page_limit=max_pages,
        timeout_sec=timeout_sec,
        retry_max=retry_max,
        retry_backoff_sec=retry_backoff_sec,
    )

    parsed_inventory = _normalize_inventory_rows(inventory_rows)
    parsed_inventory = [row for row in parsed_inventory if row["location_id"] > 0]

    location_filter = {x for x in (location_ids or []) if x > 0}
    if location_filter:
        locations = [loc for loc in locations if _to_int(loc.get("id"), -1) in location_filter]
        parsed_inventory = [row for row in parsed_inventory if row["location_id"] in location_filter]

    product_filter = {x for x in (product_ids or []) if x > 0}
    if product_filter:
        parsed_inventory = [row for row in parsed_inventory if row["product_id"] in product_filter]

    product_name_map = _fetch_product_names(
        cfg=cfg,
        product_ids=[row["product_id"] for row in parsed_inventory],
        timeout_sec=timeout_sec,
        retry_max=retry_max,
        retry_backoff_sec=retry_backoff_sec,
    )

    location_meta: Dict[int, Dict] = {}
    for loc in locations:
        loc_id = _to_int(loc.get("id"), -1)
        if loc_id <= 0:
            continue
        location_meta[loc_id] = {
            "location_name": str(loc.get("label") or loc.get("name") or f"Location {loc_id}"),
            "capacity": 500,
            "safety_stock": 50,
            "shipping_cost": 3.0,
            "service_level": 0.9,
        }

    by_product: Dict[tuple[int, int | None], Dict] = {}
    per_location_counts: Dict[int, int] = {}
    per_location_limit = int(products_per_location) if int(products_per_location) > 0 else 0

    for row in parsed_inventory:
        loc_id = _to_int(row.get("location_id"), -1)
        if loc_id <= 0:
            continue
        per_location_counts[loc_id] = per_location_counts.get(loc_id, 0)
        if per_location_limit > 0 and per_location_counts[loc_id] >= per_location_limit:
            continue

        product_id = _to_int(row.get("product_id"), -1)
        if product_id <= 0:
            continue

        variant_id_raw = row.get("variant_id")
        variant_id = _to_int(variant_id_raw, 0) if variant_id_raw is not None else None
        if variant_id == 0:
            variant_id = None

        key = (product_id, variant_id)
        product_row = by_product.setdefault(
            key,
            {
                "product_id": product_id,
                "variant_id": variant_id,
                "sku": str(row.get("sku") or ""),
                "product_name": product_name_map.get(product_id, f"Product {product_id}"),
                "total_inventory_level": 0,
                "locations": [],
            },
        )

        qty = max(_to_int(row.get("inventory_level"), 0), 0)
        meta = location_meta.get(loc_id, {"location_name": f"Location {loc_id}"})

        product_row["total_inventory_level"] += qty
        product_row["locations"].append(
            {
                "location_id": loc_id,
                "location_name": str(meta.get("location_name") or f"Location {loc_id}"),
                "inventory_level": qty,
                "availability": _availability_label(qty),
                "capacity": int(meta.get("capacity", 500)),
                "safety_stock": int(meta.get("safety_stock", 50)),
                "shipping_cost": float(meta.get("shipping_cost", 3.0)),
                "service_level": float(meta.get("service_level", 0.9)),
            }
        )
        per_location_counts[loc_id] += 1

    products = list(by_product.values())
    products.sort(key=lambda x: (int(x.get("product_id", 0)), str(x.get("variant_id") or "")))

    if not include_csv_data:
        return products

    csv_path = Path(location_products_csv_path) if location_products_csv_path else _resolve_location_products_csv_path()
    csv_rows = _read_location_products_csv_rows(csv_path)
    if not csv_rows:
        return products

    return _merge_csv_products_with_bigcommerce(products, csv_rows)
