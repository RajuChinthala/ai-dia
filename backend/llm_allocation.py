from __future__ import annotations

import json
import os
from typing import Dict, List, Optional, Tuple

import requests

from .allocation import _compute_fill_rate


def _extract_json(text: str) -> Dict:
    cleaned = text.strip()
    if "```" in cleaned:
        cleaned = cleaned.replace("```json", "```").replace("```", "").strip()
    if cleaned.startswith("{") and cleaned.endswith("}"):
        return json.loads(cleaned)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("LLM response did not include JSON.")
    return json.loads(cleaned[start : end + 1])


def _normalize_allocations(
    raw_allocations: List[Dict],
    locations: List[Dict],
    inbound: int,
) -> Tuple[List[Dict], int]:
    loc_map = {int(loc["location_id"]): loc for loc in locations}
    ordered_ids = []
    cleaned = []
    for row in raw_allocations:
        try:
            loc_id = int(row.get("location_id"))
        except Exception:
            continue
        if loc_id not in loc_map:
            continue
        ordered_ids.append(loc_id)
        cleaned.append(row)

    alloc_map: Dict[int, Dict] = {}
    for loc_id in ordered_ids:
        alloc_map.setdefault(loc_id, {"quantity": 0, "rationale": "LLM suggested"})

    for row in cleaned:
        loc_id = int(row["location_id"])
        loc = loc_map[loc_id]
        qty = int(float(row.get("quantity", 0)))
        qty = max(qty, 0)
        cap_left = max(loc["capacity"] - loc["inventory_level"], 0)
        need = max(loc["demand_forecast"] + loc.get("safety_stock", 0) - loc["inventory_level"], 0)
        qty = min(qty, cap_left, need)
        rationale = row.get("rationale") or "LLM suggested"
        alloc_map[loc_id] = {"quantity": qty, "rationale": rationale}

    ordered = [loc_id for loc_id in ordered_ids if loc_id in alloc_map]
    total = sum(alloc_map[loc_id]["quantity"] for loc_id in ordered)
    inbound_remaining = max(inbound - total, 0)
    if total > inbound:
        remaining = inbound
        for loc_id in ordered:
            qty = alloc_map[loc_id]["quantity"]
            alloc_map[loc_id]["quantity"] = max(min(qty, remaining), 0)
            remaining -= alloc_map[loc_id]["quantity"]
        inbound_remaining = remaining

    decisions = []
    for loc_id in ordered:
        loc = loc_map[loc_id]
        qty = alloc_map[loc_id]["quantity"]
        decisions.append(
            {
                "location_id": loc_id,
                "quantity": qty,
                "rationale": alloc_map[loc_id]["rationale"],
                "estimated_cost": round(qty * loc.get("shipping_cost", 0.0), 2),
            }
        )
    return decisions, inbound_remaining


def _build_llm_messages(product_id: str, inbound: int, locations: List[Dict]) -> List[Dict]:
    return [
        {
            "role": "system",
            "content": (
                "You are an inventory allocation optimizer. Return only JSON. "
                "Allocate inbound units across locations to meet demand and safety stock, "
                "respecting capacity and inventory levels."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "product_id": product_id,
                    "inbound": inbound,
                    "locations": locations,
                    "output_schema": {
                        "allocations": [
                            {
                                "location_id": 1001,
                                "quantity": 120,
                                "rationale": "High demand and service level",
                            }
                        ]
                    },
                    "rules": [
                        "quantity must be >= 0",
                        "sum(quantity) <= inbound",
                        "quantity <= capacity - inventory_level",
                        "quantity <= demand_forecast + safety_stock - inventory_level",
                    ],
                }
            ),
        },
    ]


def _candidate_endpoints(base_url: str) -> List[str]:
    trimmed = base_url.rstrip("/")
    if trimmed.endswith(("/api/chat", "/api/generate", "/v1/chat/completions")):
        return [trimmed]
    return [
        f"{trimmed}/api/chat",
        f"{trimmed}/v1/chat/completions",
        f"{trimmed}/api/generate",
    ]


def _extract_content(data: Dict, endpoint: str) -> Optional[str]:
    if endpoint.endswith("/v1/chat/completions"):
        choices = data.get("choices") if isinstance(data, dict) else None
        if choices and isinstance(choices, list):
            message = choices[0].get("message") if isinstance(choices[0], dict) else None
            if isinstance(message, dict):
                return message.get("content")
            text = choices[0].get("text")
            return text
    if endpoint.endswith("/api/chat"):
        if isinstance(data, dict) and isinstance(data.get("message"), dict):
            return data["message"].get("content")
    if endpoint.endswith("/api/generate"):
        if isinstance(data, dict):
            return data.get("response")
    return None


def llm_optimize_allocation(
    product_id: str,
    inbound: int,
    locations: List[Dict],
    model: Optional[str] = None,
    url: Optional[str] = None,
    timeout: Optional[int] = None,
) -> Dict:
    llm_url = url or os.getenv("LLM_URL", "http://localhost:11434")
    llm_model = model or os.getenv("LLM_MODEL", "llama3.2:3b")
    llm_timeout = timeout or int(os.getenv("LLM_TIMEOUT", "300"))

    messages = _build_llm_messages(product_id, inbound, locations)
    prompt = "\n".join([f"{m['role']}: {m['content']}" for m in messages])

    parsed = None
    last_error = None
    for endpoint in _candidate_endpoints(llm_url):
        try:
            if endpoint.endswith("/api/generate"):
                payload = {"model": llm_model, "prompt": prompt, "stream": False}
            else:
                payload = {"model": llm_model, "messages": messages, "stream": False}
            response = requests.post(endpoint, json=payload, timeout=llm_timeout)
            if response.status_code == 404:
                last_error = f"404 Not Found at {endpoint}"
                continue
            response.raise_for_status()
            data = response.json()
            content = _extract_content(data, endpoint)
            if not content:
                last_error = f"LLM response missing content from {endpoint}"
                continue
            parsed = _extract_json(content)
            break
        except Exception as exc:
            last_error = str(exc)
            parsed = None
            continue

    if not parsed:
        raise ValueError(
            f"LLM request failed. Last error: {last_error}. "
            "Set LLM_URL to your base endpoint, e.g. http://localhost:11434"
        )
    raw_allocations = parsed.get("allocations")
    if not isinstance(raw_allocations, list) or not raw_allocations:
        raise ValueError("LLM response missing allocations.")

    decisions, inbound_remaining = _normalize_allocations(raw_allocations, locations, inbound)

    updated_locations = [loc.copy() for loc in locations]
    alloc_map = {row["location_id"]: row["quantity"] for row in decisions}
    for loc in updated_locations:
        loc_id = int(loc["location_id"])
        loc["inventory_level"] += int(alloc_map.get(loc_id, 0))

    total_cost = sum(row["estimated_cost"] for row in decisions)
    fill_rate = _compute_fill_rate(updated_locations)

    return {
        "product_id": product_id,
        "allocations": decisions,
        "inbound_remaining": inbound_remaining,
        "estimated_total_cost": round(total_cost, 2),
        "fill_rate": fill_rate,
    }
