from __future__ import annotations

import json
import os
import re
import time
import ast
from dataclasses import dataclass
from urllib.parse import urlparse
from pathlib import Path
from typing import Dict, List

import requests

from . import chroma_memory


def _moving_average(values: List[float], window: int) -> float:
    if not values:
        return 0.0
    if len(values) < window:
        return sum(values) / len(values)
    return sum(values[-window:]) / window


def _trend(values: List[float]) -> float:
    if len(values) < 2:
        return 0.0
    x_mean = (len(values) - 1) / 2
    y_mean = sum(values) / len(values)
    num = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
    den = sum((i - x_mean) ** 2 for i in range(len(values)))
    return num / den if den else 0.0


def _seasonality(values: List[float], period: int = 7) -> float:
    if len(values) < period * 2:
        return 0.0
    current = sum(values[-period:]) / period
    prior = sum(values[-2 * period : -period]) / period
    return current - prior


@dataclass
class LLMConfig:
    api_key: str
    api_base: str
    model: str
    timeout_sec: int
    retry_max: int
    retry_backoff_sec: float
    request_max_sec: int
    retry_after_cap_sec: float
    max_tokens: int


_ENDPOINT_CACHE: Dict[str, str] = {}


def _is_local_base(api_base: str) -> bool:
    lowered = (api_base or "").lower().strip()
    if not lowered:
        return False

    if "localhost" in lowered or "127.0.0.1" in lowered or "ollama" in lowered:
        return True

    try:
        host = (urlparse(lowered).hostname or "").lower()
    except Exception:
        host = ""

    return host in {"localhost", "127.0.0.1", "ollama"}


def _normalize_api_base(api_base: str) -> str:
    normalized = (api_base or "").rstrip("/")
    if _is_local_base(normalized) and not normalized.lower().endswith("/v1"):
        return f"{normalized}/v1"
    return normalized


def _default_model_for_base(api_base: str) -> str:
    lowered = (api_base or "").lower()
    if "api.openai.com" in lowered:
        return "gpt-4o-mini"
    if "localhost" in lowered or "127.0.0.1" in lowered or "ollama" in lowered:
        return "llama3.2:3b"
    return "gpt-4o-mini"


def _read_dotenv_value(var_name: str) -> str:
    candidates = [
        Path.cwd() / ".env",
        Path.cwd() / ".env.local",
        Path.cwd() / "backend" / ".env",
        Path.cwd() / "backend" / ".env.local",
    ]

    pattern = re.compile(
        rf"^\s*{re.escape(var_name)}\s*=\s*['\"]?([^'\"\n\r#]+)['\"]?\s*$",
        re.MULTILINE,
    )

    for path in candidates:
        if not path.exists() or not path.is_file():
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        match = pattern.search(content)
        if match:
            return match.group(1).strip()

    return ""


def _get_config_value(var_name: str, default: str = "") -> str:
    value = (os.getenv(var_name) or "").strip()
    if value:
        return value

    dotenv_value = _read_dotenv_value(var_name)
    if dotenv_value:
        return dotenv_value

    return default


def _as_bool(value: str, default: bool = False) -> bool:
    text = (value or "").strip().lower()
    if not text:
        return default
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _load_config() -> LLMConfig:
    use_local_model = _as_bool(_get_config_value("USE_LOCAL_MODEL", "false"), default=False)

    if use_local_model:
        api_base = _normalize_api_base(_get_config_value("LOCAL_LLM_API_BASE", "http://localhost:11434"))
        model = _get_config_value("LOCAL_LLM_MODEL", "llama3.2:3b")
        api_key = _get_config_value("LOCAL_LLM_API_KEY", "").strip()
    else:
        api_base = _normalize_api_base(_get_config_value("LLM_API_BASE", "https://api.openai.com/v1"))
        model = _get_config_value("LLM_MODEL", _default_model_for_base(api_base))
        api_key = (_get_config_value("LLM_API_KEY") or _get_config_value("OPENAI_API_KEY")).strip()

    if not api_key and not _is_local_base(api_base):
        raise ValueError(
            "Missing LLM API key. Set LLM_API_KEY (or OPENAI_API_KEY) for hosted providers, "
            "or set USE_LOCAL_MODEL=true with LOCAL_LLM_API_BASE/LOCAL_LLM_MODEL for local Ollama."
        )

    timeout_default = "90" if _is_local_base(api_base) else "45"
    timeout_raw = _get_config_value("LLM_TIMEOUT_SEC", timeout_default)
    try:
        timeout_sec = max(5, int(timeout_raw))
    except ValueError:
        timeout_sec = 45

    retry_max_raw = _get_config_value("LLM_RETRY_MAX", "3")
    try:
        retry_max = min(max(int(retry_max_raw), 0), 8)
    except ValueError:
        retry_max = 3

    retry_backoff_raw = _get_config_value("LLM_RETRY_BACKOFF_SEC", "1.0")
    try:
        retry_backoff_sec = max(float(retry_backoff_raw), 0.1)
    except ValueError:
        retry_backoff_sec = 1.0

    request_max_default = "180" if _is_local_base(api_base) else "75"
    request_max_raw = _get_config_value("LLM_REQUEST_MAX_SEC", request_max_default)
    try:
        request_max_sec = min(max(int(request_max_raw), 10), 600)
    except ValueError:
        request_max_sec = 75

    retry_after_cap_raw = _get_config_value("LLM_RETRY_AFTER_CAP_SEC", "8")
    try:
        retry_after_cap_sec = min(max(float(retry_after_cap_raw), 0.5), 120.0)
    except ValueError:
        retry_after_cap_sec = 8.0

    max_tokens_default = "2048" if _is_local_base(api_base) else "512"
    max_tokens_raw = _get_config_value("LLM_MAX_TOKENS", max_tokens_default)
    try:
        max_tokens = min(max(int(max_tokens_raw), 64), 4096)
    except ValueError:
        max_tokens = 2048 if _is_local_base(api_base) else 512

    return LLMConfig(
        api_key=api_key,
        api_base=api_base,
        model=model,
        timeout_sec=timeout_sec,
        retry_max=retry_max,
        retry_backoff_sec=retry_backoff_sec,
        request_max_sec=request_max_sec,
        retry_after_cap_sec=retry_after_cap_sec,
        max_tokens=max_tokens,
    )


def _strip_json_fences(text: str) -> str:
    stripped = (text or "").strip()
    fence_match = re.match(r"^```(?:json)?\s*([\s\S]*?)\s*```$", stripped, flags=re.IGNORECASE)
    if fence_match:
        return fence_match.group(1).strip()
    return stripped


def _extract_braced_candidates(text: str) -> List[str]:
    candidates: List[str] = []
    stack: List[int] = []

    for index, ch in enumerate(text):
        if ch == "{":
            stack.append(index)
        elif ch == "}" and stack:
            start = stack.pop()
            if not stack:
                candidates.append(text[start : index + 1])

    return candidates


def _close_truncated_json(text: str) -> str:
    stack: List[str] = []
    in_string = False
    escaped = False

    for ch in text:
        if in_string:
            if escaped:
                escaped = False
                continue
            if ch == "\\":
                escaped = True
                continue
            if ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
        elif ch == "{":
            stack.append("}")
        elif ch == "[":
            stack.append("]")
        elif ch == "}" and stack and stack[-1] == "}":
            stack.pop()
        elif ch == "]" and stack and stack[-1] == "]":
            stack.pop()

    fixed = text
    if in_string:
        fixed += '"'
    if stack:
        fixed += "".join(reversed(stack))
    return fixed


def _try_parse_object(raw_text: str) -> Dict | None:
    text = (raw_text or "").strip()
    if not text:
        return None

    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass

    without_trailing_commas = re.sub(r",(\s*[}\]])", r"\1", text)
    if without_trailing_commas != text:
        try:
            parsed = json.loads(without_trailing_commas)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass

    try:
        parsed = ast.literal_eval(text)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass

    repaired = _close_truncated_json(text)
    if repaired != text:
        try:
            parsed = json.loads(repaired)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass

    return None


def _extract_json_object(text: str) -> Dict:
    normalized = _strip_json_fences(text)

    parsed = _try_parse_object(normalized)
    if isinstance(parsed, dict):
        return parsed

    candidates = _extract_braced_candidates(normalized)
    for candidate in candidates:
        parsed = _try_parse_object(candidate)
        if isinstance(parsed, dict):
            return parsed

    excerpt = normalized[:200].replace("\n", " ")
    raise ValueError(f"LLM response did not include a valid JSON object. excerpt='{excerpt}'")


def _retry_after_seconds(response: requests.Response) -> float:
    header = (response.headers.get("Retry-After") or "").strip()
    if not header:
        return 0.0
    try:
        return max(float(header), 0.0)
    except Exception:
        return 0.0


def _response_detail(response: requests.Response) -> str:
    try:
        payload = response.json()
        return str(payload.get("error") or payload)
    except Exception:
        return (response.text or "")[:400]


def _candidate_endpoints(api_base: str) -> List[str]:
    trimmed = (api_base or "").rstrip("/")
    lowered = trimmed.lower()
    allow_generate_fallback = _as_bool(
        _get_config_value("LLM_ALLOW_GENERATE_FALLBACK", "false"),
        default=False,
    )

    if lowered.endswith("/v1/chat/completions") or lowered.endswith("/api/chat") or lowered.endswith("/api/generate"):
        return [trimmed]

    if "api.openai.com" in lowered:
        if lowered.endswith("/v1"):
            candidates = [f"{trimmed}/chat/completions"]
        else:
            candidates = [f"{trimmed}/v1/chat/completions"]
    elif lowered.endswith("/v1"):
        base_root = trimmed[: -len("/v1")]
        candidates = [f"{trimmed}/chat/completions", f"{base_root}/api/chat"]
        if allow_generate_fallback:
            candidates.append(f"{base_root}/api/generate")
    else:
        candidates = [f"{trimmed}/api/chat", f"{trimmed}/v1/chat/completions"]
        if allow_generate_fallback:
            candidates.append(f"{trimmed}/api/generate")

    cache_key = lowered
    cached = _ENDPOINT_CACHE.get(cache_key)
    if cached:
        ordered = [cached] + [candidate for candidate in candidates if candidate != cached]
        return ordered

    return candidates


def _build_messages(system_prompt: str, user_payload: Dict) -> List[Dict]:
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": json.dumps(user_payload, separators=(",", ":"))},
    ]


def _build_request_payload(endpoint: str, model: str, messages: List[Dict], max_tokens: int) -> Dict:
    lowered = endpoint.lower()
    is_local_endpoint = _is_local_base(endpoint)

    if lowered.endswith("/api/generate"):
        prompt = "\n".join(f"{message['role']}: {message['content']}" for message in messages)
        return {
            "model": model,
            "prompt": prompt,
            "format": "json",
            "options": {
                "num_predict": max_tokens,
                "temperature": 0.1,
            },
            "stream": False,
        }

    if lowered.endswith("/api/chat"):
        return {
            "model": model,
            "messages": messages,
            "format": "json",
            "options": {
                "num_predict": max_tokens,
                "temperature": 0.1,
            },
            "stream": False,
        }

    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.1,
        "max_tokens": max_tokens,
        "stream": False,
    }
    if is_local_endpoint and lowered.endswith("/v1/chat/completions"):
        payload["response_format"] = {"type": "json_object"}
    return payload


def _extract_content_from_payload(payload: Dict, endpoint: str) -> str:
    lowered = endpoint.lower()

    if lowered.endswith("/v1/chat/completions"):
        choices = payload.get("choices") if isinstance(payload, dict) else None
        if isinstance(choices, list) and choices:
            first = choices[0] if isinstance(choices[0], dict) else {}
            message = first.get("message") if isinstance(first, dict) else None
            if isinstance(message, dict):
                content = message.get("content")
                if isinstance(content, str):
                    return content
                if isinstance(content, list):
                    return "".join(
                        chunk.get("text", "") if isinstance(chunk, dict) else str(chunk)
                        for chunk in content
                    )
            text = first.get("text") if isinstance(first, dict) else None
            if isinstance(text, str):
                return text
        raise ValueError("LLM response missing content in choices/message.")

    if lowered.endswith("/api/chat"):
        message = payload.get("message") if isinstance(payload, dict) else None
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, str):
                return content
        raise ValueError("LLM /api/chat response missing message.content.")

    if lowered.endswith("/api/generate"):
        content = payload.get("response") if isinstance(payload, dict) else None
        if isinstance(content, str):
            return content
        raise ValueError("LLM /api/generate response missing response field.")

    raise ValueError(f"Unsupported LLM endpoint format: {endpoint}")


def _chat_json(*, cfg: LLMConfig, system_prompt: str, user_payload: Dict) -> Dict:
    headers = {"Content-Type": "application/json"}
    if cfg.api_key:
        headers["Authorization"] = f"Bearer {cfg.api_key}"
    messages = _build_messages(system_prompt, user_payload)
    started_at = time.monotonic()
    cache_key = (cfg.api_base or "").rstrip("/").lower()

    def _seconds_left() -> float:
        return max(float(cfg.request_max_sec) - (time.monotonic() - started_at), 0.0)

    def _request_timeout() -> tuple[int, int]:
        remaining = _seconds_left()
        if remaining <= 0:
            raise TimeoutError("LLM request budget exhausted")
        read_timeout = max(1, int(min(float(cfg.timeout_sec), remaining)))
        connect_timeout = max(1, min(5, read_timeout))
        return (connect_timeout, read_timeout)

    def _sleep_with_budget(seconds: float) -> bool:
        remaining = _seconds_left()
        if remaining <= 0:
            return False
        time.sleep(min(max(seconds, 0.0), remaining))
        return True

    last_error = ""
    for endpoint in _candidate_endpoints(cfg.api_base):
        body = _build_request_payload(endpoint, cfg.model, messages, cfg.max_tokens)
        response = None
        endpoint_failed = False

        for attempt in range(cfg.retry_max + 1):
            try:
                response = requests.post(endpoint, headers=headers, json=body, timeout=_request_timeout())
            except requests.RequestException as exc:
                last_error = f"{endpoint}: request error: {exc}"
                endpoint_failed = True
                if attempt >= cfg.retry_max:
                    break
                if not _sleep_with_budget(cfg.retry_backoff_sec * (2 ** attempt)):
                    last_error = f"{endpoint}: request timed out after {cfg.request_max_sec}s budget"
                    break
                continue
            except TimeoutError:
                last_error = f"{endpoint}: request timed out after {cfg.request_max_sec}s budget"
                endpoint_failed = True
                break

            if response.status_code == 429:
                if attempt >= cfg.retry_max:
                    detail = _response_detail(response)
                    raise ValueError(
                        "LLM provider rate-limited requests (HTTP 429) after retries. "
                        "Reduce request frequency, check provider quota, or switch to local Ollama. "
                        f"Provider detail: {detail}"
                    )
                wait = _retry_after_seconds(response)
                if wait <= 0:
                    wait = cfg.retry_backoff_sec * (2 ** attempt)
                wait = min(wait, cfg.retry_after_cap_sec)
                if not _sleep_with_budget(wait):
                    last_error = f"{endpoint}: request timed out after {cfg.request_max_sec}s budget"
                    endpoint_failed = True
                    break
                continue

            if response.status_code == 404:
                detail = _response_detail(response)
                last_error = f"{endpoint}: 404 not found: {detail}"
                endpoint_failed = True
                break

            if 500 <= response.status_code < 600:
                if attempt >= cfg.retry_max:
                    detail = _response_detail(response)
                    last_error = f"{endpoint}: provider server error (HTTP {response.status_code}): {detail}"
                    endpoint_failed = True
                    break
                if not _sleep_with_budget(cfg.retry_backoff_sec * (2 ** attempt)):
                    last_error = f"{endpoint}: request timed out after {cfg.request_max_sec}s budget"
                    endpoint_failed = True
                    break
                continue

            try:
                response.raise_for_status()
            except requests.HTTPError:
                detail = _response_detail(response)
                last_error = f"{endpoint}: HTTP {response.status_code}: {detail}"
                endpoint_failed = True
                if attempt >= cfg.retry_max:
                    break
                if not _sleep_with_budget(cfg.retry_backoff_sec * (2 ** attempt)):
                    last_error = f"{endpoint}: request timed out after {cfg.request_max_sec}s budget"
                    break
                continue

            try:
                payload = response.json()
            except ValueError:
                last_error = f"{endpoint}: invalid JSON response"
                endpoint_failed = True
                if attempt >= cfg.retry_max:
                    break
                if not _sleep_with_budget(cfg.retry_backoff_sec * (2 ** attempt)):
                    last_error = f"{endpoint}: request timed out after {cfg.request_max_sec}s budget"
                    break
                continue

            try:
                content = _extract_content_from_payload(payload, endpoint)
                parsed = _extract_json_object(str(content))
            except ValueError as exc:
                last_error = f"{endpoint}: parse error: {exc}"
                endpoint_failed = True
                if attempt >= cfg.retry_max:
                    break
                if not _sleep_with_budget(cfg.retry_backoff_sec * (2 ** attempt)):
                    last_error = f"{endpoint}: request timed out after {cfg.request_max_sec}s budget"
                    break
                continue

            _ENDPOINT_CACHE[cache_key] = endpoint
            return parsed

        if endpoint_failed and _ENDPOINT_CACHE.get(cache_key) == endpoint:
            _ENDPOINT_CACHE.pop(cache_key, None)

    raise ValueError(
        "LLM request failed across candidate endpoints. "
        f"base='{cfg.api_base}', model='{cfg.model}', last_error='{last_error}'. "
        "If using OpenAI, set USE_LOCAL_MODEL=false, LLM_API_BASE='https://api.openai.com/v1', and an OpenAI model. "
        "If using local Ollama, set USE_LOCAL_MODEL=true, LOCAL_LLM_API_BASE='http://localhost:11434' (or '/v1'), "
        "LOCAL_LLM_MODEL='llama3.2:3b', ensure 'ollama serve' is running and the model is pulled, and increase "
        "LLM_REQUEST_MAX_SEC/LLM_TIMEOUT_SEC for slow first-run model loads."
    )


def _to_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_int(value, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _history_summary(history: List[Dict], product_id: str) -> List[Dict]:
    grouped: Dict[int, Dict[str, List[float]]] = {}
    for row in history:
        if str(row.get("product_id")) != str(product_id):
            continue
        loc_id = _to_int(row.get("location_id"), -1)
        if loc_id < 0:
            continue
        slot = grouped.setdefault(
            loc_id,
            {
                "units": [],
                "weather": [],
                "social": [],
                "event": [],
            },
        )
        slot["units"].append(_to_float(row.get("units"), 0.0))
        slot["weather"].append(_to_float(row.get("weather_score"), 0.0))
        slot["social"].append(_to_float(row.get("social_signal"), 0.0))
        slot["event"].append(_to_float(row.get("event_score"), 0.0))

    summaries: List[Dict] = []
    for loc_id, values in grouped.items():
        units = values["units"]
        weather = values["weather"]
        social = values["social"]
        event = values["event"]
        summaries.append(
            {
                "location_id": loc_id,
                "obs_days": len(units),
                "avg_units_7d": round(_moving_average(units, 7), 3),
                "trend_daily": round(_trend(units), 3),
                "seasonal_weekly_delta": round(_seasonality(units, 7), 3),
                "weather_7d": round(_moving_average(weather, 7), 3),
                "social_7d": round(_moving_average(social, 7), 3),
                "event_7d": round(_moving_average(event, 7), 3),
            }
        )

    summaries.sort(key=lambda x: int(x["location_id"]))
    return summaries


def _sanitize_specialist_outputs(
    *, llm_result: Dict, locations: List[Dict], horizon: int
) -> List[Dict]:
    by_loc: Dict[int, Dict] = {}
    raw = llm_result.get("specialist_outputs", [])
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            loc_id = _to_int(item.get("location_id"), -1)
            if loc_id < 0:
                continue
            by_loc[loc_id] = item

    specialist_outputs: List[Dict] = []
    for loc in locations:
        loc_id = _to_int(loc.get("location_id"), -1)
        item = by_loc.get(loc_id, {})

        sales_base_daily = max(_to_float(item.get("sales_base_daily"), 0.0), 0.0)
        sales_trend_daily = _to_float(item.get("sales_trend_daily"), 0.0)
        seasonal_weekly_delta = _to_float(item.get("seasonal_weekly_delta"), 0.0)
        weather_daily_impact = _to_float(item.get("weather_daily_impact"), 0.0)
        social_daily_impact = _to_float(item.get("social_daily_impact"), 0.0)

        final_daily_forecast = _to_float(item.get("final_daily_forecast"), None)
        if final_daily_forecast is None:
            final_daily_forecast = (
                sales_base_daily
                + sales_trend_daily
                + seasonal_weekly_delta
                + weather_daily_impact
                + social_daily_impact
            )
        final_daily_forecast = max(final_daily_forecast, 0.0)

        final_period_forecast = _to_int(item.get("final_period_forecast"), -1)
        if final_period_forecast < 0:
            final_period_forecast = int(round(final_daily_forecast * horizon))

        specialist_outputs.append(
            {
                "location_id": loc_id,
                "sales_base_daily": round(sales_base_daily, 2),
                "sales_trend_daily": round(sales_trend_daily, 2),
                "seasonal_weekly_delta": round(seasonal_weekly_delta, 2),
                "weather_daily_impact": round(weather_daily_impact, 2),
                "social_daily_impact": round(social_daily_impact, 2),
                "final_daily_forecast": round(final_daily_forecast, 2),
                "final_period_forecast": max(final_period_forecast, 0),
            }
        )

    return specialist_outputs


def _sanitize_allocations(*, llm_result: Dict, locations: List[Dict], inbound: int) -> Dict:
    location_ids = {_to_int(loc.get("location_id"), -1) for loc in locations}
    raw = llm_result.get("allocations", [])
    decisions: List[Dict] = []

    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            loc_id = _to_int(item.get("location_id"), -1)
            if loc_id not in location_ids:
                continue
            qty = _to_int(item.get("quantity"), 0)
            rationale = str(item.get("rationale") or "LLM allocation")
            est_cost = _to_float(item.get("estimated_cost"), 0.0)
            decisions.append(
                {
                    "location_id": loc_id,
                    "quantity": qty,
                    "rationale": rationale,
                    "estimated_cost": round(max(est_cost, 0.0), 2),
                }
            )

    inbound_used = sum(max(0, int(d["quantity"])) for d in decisions)
    inbound_remaining = max(inbound - inbound_used, 0)

    total_cost = sum(_to_float(d.get("estimated_cost"), 0.0) for d in decisions)
    fill_rate = _to_float(llm_result.get("fill_rate"), -1.0)
    if fill_rate < 0.0:
        fill_rate = 0.0

    return {
        "allocations": decisions,
        "inbound_remaining": inbound_remaining,
        "estimated_total_cost": round(max(total_cost, 0.0), 2),
        "fill_rate": round(min(max(fill_rate, 0.0), 1.0), 3),
    }


def _compact_retrieved_cases(similar_cases: List[Dict], limit: int = 3) -> List[Dict]:
    compact: List[Dict] = []
    for row in similar_cases[:limit]:
        metadata = row.get("metadata") if isinstance(row, dict) else {}
        record = row.get("record") if isinstance(row, dict) else {}
        allocations = record.get("allocations", []) if isinstance(record, dict) else []
        specialist_outputs = record.get("specialist_outputs", []) if isinstance(record, dict) else []
        compact.append(
            {
                "distance": _to_float(row.get("distance"), -1.0),
                "product_id": str((metadata or {}).get("product_id") or (record or {}).get("product_id") or ""),
                "horizon": _to_int((metadata or {}).get("horizon"), _to_int((record or {}).get("horizon"), 0)),
                "inbound": _to_int((metadata or {}).get("inbound"), _to_int((record or {}).get("inbound"), 0)),
                "fill_rate": round(
                    _to_float((metadata or {}).get("fill_rate"), _to_float((record or {}).get("fill_rate"), 0.0)),
                    3,
                ),
                "allocations": allocations[:5] if isinstance(allocations, list) else [],
                "specialist_outputs": specialist_outputs[:5] if isinstance(specialist_outputs, list) else [],
            }
        )
    return compact


def _build_retrieval_context(
    *,
    product_id: str,
    horizon: int,
    inbound: int,
    summary: List[Dict],
    locations: List[Dict],
    similar_cases: List[Dict],
) -> Dict:
    compact_cases = _compact_retrieved_cases(similar_cases, limit=3)

    avg_units = [_to_float(row.get("avg_units_7d"), 0.0) for row in summary]
    trend_values = [_to_float(row.get("trend_daily"), 0.0) for row in summary]
    retrieval_insights = [
        f"retrieved_case_count={len(compact_cases)}",
        f"summary_location_count={len(summary)}",
        f"avg_units_7d_mean={round(sum(avg_units) / len(avg_units), 3) if avg_units else 0.0}",
        f"trend_mean={round(sum(trend_values) / len(trend_values), 3) if trend_values else 0.0}",
    ]

    return {
        "query": {
            "product_id": str(product_id),
            "horizon": int(horizon),
            "inbound": int(inbound),
            "location_count": len(locations),
        },
        "retrieved_cases": compact_cases,
        "retrieval_insights": retrieval_insights,
    }


def run_rag_orchestrated_pipeline(
    *,
    product_id: str,
    inbound: int,
    locations: List[Dict],
    history: List[Dict],
    horizon: int = 7,
) -> Dict:
    if not history:
        raise ValueError("RAG pipeline requires non-empty history with sales/weather/social signals.")

    cfg = _load_config()
    summary = _history_summary(history, product_id)
    if not summary:
        raise ValueError("No history rows matched product_id for RAG pipeline.")

    retrieved_rows = chroma_memory.query_similar_runs(
        product_id=product_id,
        horizon=horizon,
        inbound=inbound,
        summary=summary,
        locations=locations,
    )
    retrieval_context = _build_retrieval_context(
        product_id=product_id,
        horizon=horizon,
        inbound=inbound,
        summary=summary,
        locations=locations,
        similar_cases=retrieved_rows,
    )

    forecast_system = (
        "You are a forecasting specialist in a Retrieval-Augmented Generation (RAG) pipeline. "
        "Use retrieved_cases and retrieval_insights as supporting context, but adapt to the current query. "
        "Return ONLY valid JSON with key 'specialist_outputs'. "
        "Each item must include: location_id, sales_base_daily, sales_trend_daily, "
        "seasonal_weekly_delta, weather_daily_impact, social_daily_impact, "
        "final_daily_forecast, final_period_forecast."
    )
    forecast_user = {
        "task": "Forecast by location using history summaries + retrieved prior cases.",
        "product_id": product_id,
        "horizon": horizon,
        "history_summary": summary,
        "retrieval_context": retrieval_context,
        "locations": [
            {
                "location_id": int(loc["location_id"]),
                "capacity": int(loc.get("capacity", 0)),
                "inventory_level": int(loc.get("inventory_level", 0)),
                "safety_stock": int(loc.get("safety_stock", 0)),
            }
            for loc in locations
        ],
    }
    forecast_raw = _chat_json(cfg=cfg, system_prompt=forecast_system, user_payload=forecast_user)
    specialist_outputs = _sanitize_specialist_outputs(
        llm_result=forecast_raw,
        locations=locations,
        horizon=horizon,
    )

    enriched_locations = [loc.copy() for loc in locations]
    by_loc = {int(x["location_id"]): x for x in specialist_outputs}
    for loc in enriched_locations:
        loc_id = int(loc["location_id"])
        loc["demand_forecast"] = int(by_loc.get(loc_id, {}).get("final_period_forecast", 0))

    allocation_system = (
        "You are an allocation specialist in a Retrieval-Augmented Generation (RAG) pipeline. "
        "Use the retrieved cases as references and optimize for current demand and constraints. "
        "Return ONLY valid JSON with keys: allocations (list of location_id, quantity, rationale, estimated_cost), fill_rate. "
        "Positive quantity means inbound assigned to location; negative means transfer out."
    )
    allocation_user = {
        "task": "Allocate inbound inventory using forecast + retrieved prior allocations.",
        "product_id": product_id,
        "inbound": int(inbound),
        "horizon": horizon,
        "retrieval_context": retrieval_context,
        "locations": [
            {
                "location_id": int(loc["location_id"]),
                "location_name": loc.get("location_name"),
                "inventory_level": int(loc.get("inventory_level", 0)),
                "demand_forecast": int(loc.get("demand_forecast", 0)),
                "capacity": int(loc.get("capacity", 0)),
                "safety_stock": int(loc.get("safety_stock", 0)),
                "shipping_cost": _to_float(loc.get("shipping_cost"), 0.0),
                "service_level": _to_float(loc.get("service_level"), 0.9),
            }
            for loc in enriched_locations
        ],
    }
    allocation_raw = _chat_json(
        cfg=cfg,
        system_prompt=allocation_system,
        user_payload=allocation_user,
    )
    allocation_result = _sanitize_allocations(
        llm_result=allocation_raw,
        locations=enriched_locations,
        inbound=inbound,
    )

    chroma_memory.upsert_run_memory(
        product_id=product_id,
        horizon=horizon,
        inbound=inbound,
        summary=summary,
        locations=enriched_locations,
        specialist_outputs=specialist_outputs,
        allocations=allocation_result["allocations"],
        fill_rate=float(allocation_result["fill_rate"]),
    )

    return {
        "product_id": product_id,
        "horizon": horizon,
        # Keep backward-compatible mode label for existing clients.
        "allocation_mode": "llm",
        "specialist_outputs": specialist_outputs,
        "allocations": allocation_result["allocations"],
        "inbound_remaining": allocation_result["inbound_remaining"],
        "estimated_total_cost": allocation_result["estimated_total_cost"],
        "fill_rate": allocation_result["fill_rate"],
        "retrieval_context": retrieval_context,
    }


def run_llm_orchestrated_pipeline(
    *,
    product_id: str,
    inbound: int,
    locations: List[Dict],
    history: List[Dict],
    horizon: int = 7,
) -> Dict:
    # Backward-compatible alias retained for existing route calls/tests.
    return run_rag_orchestrated_pipeline(
        product_id=product_id,
        inbound=inbound,
        locations=locations,
        history=history,
        horizon=horizon,
    )
