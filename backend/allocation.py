"""
Simple allocation/transfer optimizer.
The goal is to honor forecasted demand + safety stock while minimizing shipping cost.
If inbound inventory is insufficient, the algorithm uses store-to-store transfers
from locations with surplus.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple


@dataclass
class AllocationDecision:
    location_id: int
    quantity: int
    rationale: str
    estimated_cost: float


def _score(need: int, cost: float, service_level: float) -> float:
    # higher score = allocate earlier
    return (need * service_level) / max(cost, 0.1)


def optimize_allocation(
    product_id: str,
    inbound: int,
    locations: List[Dict],
) -> Dict:
    """
    Greedy allocation guided by forecast need, service level, and shipping cost.
    Each location dict must include: location_id, inventory_level, demand_forecast,
    capacity, safety_stock, shipping_cost, service_level.
    """
    needs: List[Tuple[float, Dict]] = []
    surplus: List[Dict] = []

    for loc in locations:
        target = loc["demand_forecast"] + loc.get("safety_stock", 0)
        net = target - loc["inventory_level"]
        if net > 0:
            needs.append(
                (_score(net, loc.get("shipping_cost", 1.0), loc.get("service_level", 0.9)), loc)
            )
        else:
            surplus.append(loc | {"excess": abs(net)})

    needs.sort(key=lambda item: item[0], reverse=True)
    decisions: List[AllocationDecision] = []
    total_cost = 0.0
    inbound_remaining = inbound

    for _, loc in needs:
        gap = loc["demand_forecast"] + loc.get("safety_stock", 0) - loc["inventory_level"]
        gap = max(gap, 0)
        if inbound_remaining <= 0:
            break
        qty = int(min(gap, inbound_remaining, loc["capacity"] - loc["inventory_level"]))
        inbound_remaining -= qty
        total_cost += qty * loc.get("shipping_cost", 0.0)
        decisions.append(
            AllocationDecision(
                location_id=loc["location_id"],
                quantity=qty,
                rationale="Inbound allocation",
                estimated_cost=qty * loc.get("shipping_cost", 0.0),
            )
        )
        loc["inventory_level"] += qty  # update for later surplus calc

    # Rebalance between locations when demand is still not met
    outstanding_needs = []
    for _, loc in needs:
        target = loc["demand_forecast"] + loc.get("safety_stock", 0)
        if loc["inventory_level"] < target:
            outstanding_needs.append(loc)

    surplus.sort(key=lambda s: s.get("shipping_cost", 0.0))
    for loc in outstanding_needs:
        gap = loc["demand_forecast"] + loc.get("safety_stock", 0) - loc["inventory_level"]
        if gap <= 0:
            continue
        for donor in surplus:
            if donor["excess"] <= 0:
                continue
            transfer = min(gap, donor["excess"], loc["capacity"] - loc["inventory_level"])
            if transfer <= 0:
                continue
            donor["excess"] -= transfer
            gap -= transfer
            loc["inventory_level"] += transfer
            cost = transfer * ((loc.get("shipping_cost", 0.0) + donor.get("shipping_cost", 0.0)) / 2)
            total_cost += cost
            decisions.append(
                AllocationDecision(
                    location_id=loc["location_id"],
                    quantity=transfer,
                    rationale=f"Rebalance from {donor['location_id']}",
                    estimated_cost=cost,
                )
            )
            decisions.append(
                AllocationDecision(
                    location_id=donor["location_id"],
                    quantity=-transfer,
                    rationale=f"Send to {loc['location_id']}",
                    estimated_cost=cost,
                )
            )
            if gap <= 0:
                break

    fill_rate = _compute_fill_rate(locations)
    return {
        "product_id": product_id,
        "allocations": [dec.__dict__ for dec in decisions],
        "inbound_remaining": inbound_remaining,
        "estimated_total_cost": round(total_cost, 2),
        "fill_rate": fill_rate,
    }


def _compute_fill_rate(locations: List[Dict]) -> float:
    target = 0.0
    inventory = 0.0
    for loc in locations:
        target += loc["demand_forecast"]
        inventory += min(loc["inventory_level"], loc["demand_forecast"])
    return round(inventory / target, 3) if target else 0.0
