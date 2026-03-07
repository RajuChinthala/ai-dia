from __future__ import annotations

import importlib.util
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List


_CHROMA_CLIENT = None
_CHROMA_COLLECTION = None


def _as_bool(value: str, default: bool = False) -> bool:
    text = (value or "").strip().lower()
    if not text:
        return default
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _enabled() -> bool:
    return _as_bool(os.getenv("ENABLE_CHROMA_MEMORY", "true"), default=True)


def _top_k() -> int:
    raw = (os.getenv("CHROMA_TOP_K", "3") or "").strip()
    try:
        return min(max(int(raw), 1), 10)
    except ValueError:
        return 3


def _persist_dir() -> str:
    raw = (os.getenv("CHROMA_PERSIST_DIR", "data/chroma") or "").strip()
    path = Path(raw)
    if not path.is_absolute():
        path = Path.cwd() / raw
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


def _collection_name() -> str:
    return (os.getenv("CHROMA_COLLECTION", "agent_flow_runs") or "agent_flow_runs").strip()


def _chroma_host() -> str:
    return (os.getenv("CHROMA_HOST", "") or "").strip()


def _chroma_port() -> int:
    raw = (os.getenv("CHROMA_PORT", "8000") or "").strip()
    try:
        return min(max(int(raw), 1), 65535)
    except ValueError:
        return 8000


def _chroma_ssl() -> bool:
    return _as_bool(os.getenv("CHROMA_SSL", "false"), default=False)


def _get_collection():
    global _CHROMA_CLIENT, _CHROMA_COLLECTION

    if not _enabled():
        return None

    if _CHROMA_COLLECTION is not None:
        return _CHROMA_COLLECTION

    try:
        import chromadb  # type: ignore[import-not-found]
    except Exception:
        return None

    try:
        if _CHROMA_CLIENT is None:
            if _chroma_host():
                _CHROMA_CLIENT = chromadb.HttpClient(
                    host=_chroma_host(),
                    port=_chroma_port(),
                    ssl=_chroma_ssl(),
                )
            else:
                _CHROMA_CLIENT = chromadb.PersistentClient(path=_persist_dir())
        _CHROMA_COLLECTION = _CHROMA_CLIENT.get_or_create_collection(name=_collection_name())
        return _CHROMA_COLLECTION
    except Exception:
        return None


def _safe_json(value: Dict) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)


def _build_retrieval_query(
    *,
    product_id: str,
    horizon: int,
    inbound: int,
    summary: List[Dict],
    locations: List[Dict],
) -> str:
    compact_summary = [
        {
            "location_id": int(item.get("location_id", -1)),
            "avg_units_7d": float(item.get("avg_units_7d", 0.0)),
            "trend_daily": float(item.get("trend_daily", 0.0)),
            "seasonal_weekly_delta": float(item.get("seasonal_weekly_delta", 0.0)),
        }
        for item in summary[:20]
    ]
    compact_locations = [
        {
            "location_id": int(item.get("location_id", -1)),
            "inventory_level": int(item.get("inventory_level", 0)),
            "capacity": int(item.get("capacity", 0)),
            "safety_stock": int(item.get("safety_stock", 0)),
            "shipping_cost": float(item.get("shipping_cost", 0.0)),
            "service_level": float(item.get("service_level", 0.9)),
        }
        for item in locations[:30]
    ]

    payload = {
        "product_id": str(product_id),
        "horizon": int(horizon),
        "inbound": int(inbound),
        "history_summary": compact_summary,
        "locations": compact_locations,
    }
    return _safe_json(payload)


def query_similar_runs(
    *,
    product_id: str,
    horizon: int,
    inbound: int,
    summary: List[Dict],
    locations: List[Dict],
) -> List[Dict]:
    collection = _get_collection()
    if collection is None:
        return []

    query_text = _build_retrieval_query(
        product_id=product_id,
        horizon=horizon,
        inbound=inbound,
        summary=summary,
        locations=locations,
    )

    def _safe_query(where: Dict | None) -> Dict | None:
        kwargs = {
            "query_texts": [query_text],
            "n_results": _top_k(),
            "include": ["documents", "metadatas", "distances"],
        }
        if where is not None:
            kwargs["where"] = where
        try:
            return collection.query(**kwargs)
        except Exception:
            return None

    # First prefer the same product history. If that is sparse, broaden retrieval.
    result = _safe_query({"product_id": str(product_id)})
    docs = ((result or {}).get("documents") or [[]])[0]
    if not docs:
        result = _safe_query(None)
    if result is None:
        return []

    documents = (result.get("documents") or [[]])[0]
    metadatas = (result.get("metadatas") or [[]])[0]
    distances = (result.get("distances") or [[]])[0]

    rows: List[Dict] = []
    for index, document in enumerate(documents):
        metadata = metadatas[index] if index < len(metadatas) else {}
        distance = distances[index] if index < len(distances) else None
        parsed_document: Dict = {}
        if isinstance(document, str):
            try:
                parsed_document = json.loads(document)
            except Exception:
                parsed_document = {"raw": document}
        rows.append(
            {
                "distance": float(distance) if distance is not None else None,
                "metadata": metadata or {},
                "record": parsed_document,
            }
        )

    return rows


def upsert_run_memory(
    *,
    product_id: str,
    horizon: int,
    inbound: int,
    summary: List[Dict],
    locations: List[Dict],
    specialist_outputs: List[Dict],
    allocations: List[Dict],
    fill_rate: float,
) -> bool:
    collection = _get_collection()
    if collection is None:
        return False

    record = {
        "product_id": str(product_id),
        "horizon": int(horizon),
        "inbound": int(inbound),
        "history_summary": summary,
        "locations": locations,
        "specialist_outputs": specialist_outputs,
        "allocations": allocations,
        "fill_rate": float(fill_rate),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    record_id = f"{product_id}-{int(datetime.now(timezone.utc).timestamp() * 1000)}-{uuid.uuid4().hex[:8]}"
    query_text = _build_retrieval_query(
        product_id=product_id,
        horizon=horizon,
        inbound=inbound,
        summary=summary,
        locations=locations,
    )

    metadata = {
        "product_id": str(product_id),
        "horizon": int(horizon),
        "inbound": int(inbound),
        "fill_rate": float(fill_rate),
        "ts_epoch": float(datetime.now(timezone.utc).timestamp()),
    }

    try:
        collection.upsert(
            ids=[record_id],
            documents=[_safe_json(record)],
            metadatas=[metadata],
            embeddings=None,
        )
    except TypeError:
        try:
            collection.upsert(
                ids=[record_id],
                documents=[_safe_json(record)],
                metadatas=[metadata],
            )
        except Exception:
            return False
    except Exception:
        return False

    return True


def get_memory_health() -> Dict:
    enabled = _enabled()
    chromadb_installed = bool(importlib.util.find_spec("chromadb"))
    mode = "http" if _chroma_host() else "persistent"

    health: Dict = {
        "enabled": enabled,
        "chromadb_installed": chromadb_installed,
        "mode": mode,
        "collection": _collection_name(),
        "top_k": _top_k(),
    }

    if mode == "http":
        health["host"] = _chroma_host()
        health["port"] = _chroma_port()
        health["ssl"] = _chroma_ssl()
    else:
        health["persist_dir"] = _persist_dir()

    if not enabled:
        health["status"] = "disabled"
        return health

    if not chromadb_installed:
        health["status"] = "unavailable"
        health["reason"] = "chromadb package not installed"
        return health

    collection = _get_collection()
    if collection is None:
        health["status"] = "unavailable"
        health["reason"] = "unable to connect or create collection"
        return health

    health["status"] = "ok"
    try:
        health["record_count"] = int(collection.count())
    except Exception:
        health["record_count"] = None

    return health
