# Dynamic Allocation Prototype

AI-driven demand forecasting + inventory allocation demo that mirrors the Dynamic-Allocation brief. It includes:

- **Notebook** clone with new input fields and an embedded optimization run.
- **FastAPI** service exposing forecasting, allocation, and orchestrated pipeline endpoints.
- **React (Vite)** UI to load forecast inputs and run allocations.

## Project layout

- `demand_forecast_prototype.ipynb` – original notebook (unchanged).
- `notebooks/demand_forecast_updated.ipynb` – cloned notebook with product/store fields, inbound units, safety stock, and a call into the optimization engine.
- `backend/` – FastAPI app, lightweight forecaster, allocation optimizer, and pipeline orchestration.
- `frontend/` – React UI wired to the API.
- `requirements.txt` – Python dependencies (forecasting/ML + API + optimization).

## Execution steps

1) **Python environment**

Linux/macOS
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Windows PowerShell
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python.exe -m pip install --upgrade pip
```

2) **Run FastAPI service**
```bash
uvicorn backend.app:app --reload --port 8000
```
- Health: `GET http://localhost:8000/health`
- Custom forecast: `POST http://localhost:8000/forecast` with history rows
- API-source forecast (notebook-free): `POST http://localhost:8000/forecast/api` (sales + weather + social APIs)
- Custom allocation: `POST http://localhost:8000/allocate` with inbound + locations payload
- Notebook pipeline: `POST http://localhost:8000/pipeline/notebook_forecast` (execute notebook and produce final demand forecast sheet)
- Agent pipeline: `POST http://localhost:8000/pipeline/agent_forecast_allocate` (weather/season/sales specialist signals → final forecast agent → allocation)

3) **React UI (Vite)**
```bash
cd frontend
npm install
npm run dev
```
- Opens on `http://localhost:5173`; proxy sends `/api/*` to `http://localhost:8000`.
- Use the UI to load forecast inputs and run allocation optimization.
- Frontend Agent UI is trigger-only and does not require entering API URLs.
- Configure source APIs in backend config file: `backend/api_calls/config.py`.

4) **Notebook**
- Open `notebooks/demand_forecast_updated.ipynb` in Jupyter/Lab/VS Code.
- Run the new cells near the top to build extended inputs and call the allocation optimizer.

5) **CLI smoke test (no server)**

Linux/macOS
```bash
source .venv/bin/activate
python -m backend.app
```

Windows PowerShell
```powershell
.\.venv\Scripts\Activate.ps1
python -m backend.app
```
Prints forecast + allocation plan using local execution flow.

6) **Validation tests**
```bash
python -m unittest tests/test_agent_pipeline_flow.py tests/test_agent_pipeline_api.py -v
```
Validates deterministic flow and HTTP endpoint orchestration paths.

## Notes

- Data model is aligned to **BigCommerce Inventory API**: `product_id`, optional `variant_id`, `location_id`, `inventory_level` (ATS per location), safety stock, capacity, shipping cost, and service level.
- Optimizer combines forecasted demand + safety stock with shipping cost, capacity, and service level to produce allocations. Positive qty = ship in, negative qty = transfer out.
- For production usage, send real merged history rows (`units`, `weather_score`, `social_signal`) through `/pipeline/agent_forecast_allocate`.
- The updated notebook can call `/pipeline/notebook_forecast` to execute and standardize forecast outputs in CSV form.

## Agent orchestration pattern

`POST /pipeline/agent_forecast_allocate` now uses a **single LLM pipeline**:

1. Load history from source APIs (sales + weather + seasonal trend), unless `history[]` is provided.
2. Forecast LLM generates per-location demand signals and horizon forecast.
3. Allocation LLM consumes the forecast output and generates final allocations.

Request highlights:

- Source APIs are resolved from backend configuration (`backend/api_calls/config.py`) when not provided in request.
- Optional override in request: `sales_api_url`, `weather_api_url`, `seasonal_api_url`.
- Optional alias: `social_api_url` (deprecated alias for `seasonal_api_url`).
- Optional: `history[]` to bypass API fetch and directly run LLM stages.
- `horizon`: forecast horizon in days.
- Built-in source API resilience: retries, 429 handling (`Retry-After`), and normalized weather/social features.
- Notebook-equivalent built-ins:
   - `weather_api_url=builtin://weather?city=OHIO&lat=40.1088&lon=-82.9742&days=4`
     - Optional `api_key=<OPENWEATHER_KEY>` or `OPENWEATHER_API_KEY` env var enriches with future weather; without key it uses Open-Meteo history only.
   - `sales_api_url=builtin://sales?days=14&products=5&seed=42`
   - `seasonal_api_url=builtin://social?days=14&seed=42`

UI integration note:

- Frontend should call only `POST /pipeline/agent_forecast_allocate` for planning flow.
- Do not call `POST /forecast/api` directly from UI; it is a backend support endpoint used by pipeline Option 1 when source API URLs are provided.

Response highlights:

- `specialist_outputs[]` contains each specialist signal plus final demand forecast by location.
- Allocation decision fields (`allocations`, `inbound_remaining`, `estimated_total_cost`, `fill_rate`).

This gives you LLM-based forecast and LLM-based allocation in one endpoint.

## LLM setup

The agent pipeline always uses LLM for both forecast and allocation.

### Required env vars

- `LLM_API_KEY` (or `OPENAI_API_KEY`) for hosted providers like OpenAI
- For local Ollama (`localhost`/`127.0.0.1`), key is optional
- Optional:
   - `USE_LOCAL_MODEL` (`true`/`false`, default `false`)
   - `LLM_API_BASE` (default `https://api.openai.com/v1`)
   - `LLM_MODEL` (default `gpt-4o-mini`)
   - `LLM_TIMEOUT_SEC` (default `45`)
   - `LLM_RETRY_MAX` (default `3`)
   - `LLM_RETRY_BACKOFF_SEC` (default `1.0`)

### Local Ollama setup

Use these values in `.env` when Ollama is running locally:

- `USE_LOCAL_MODEL=true`
- `LOCAL_LLM_API_BASE=http://localhost:11434`
- `LOCAL_LLM_MODEL=llama3.2:3b`
- `LOCAL_LLM_API_KEY=` (optional for local)

For hosted providers (OpenAI), set `USE_LOCAL_MODEL=false` and use:

- `LLM_API_BASE=https://api.openai.com/v1`
- `LLM_MODEL=gpt-4o-mini`
- `LLM_API_KEY=<your_key>` (or `OPENAI_API_KEY`)

### Request behavior

- Provide `history[]` directly, or provide source URLs (`sales_api_url`, `weather_api_url`, `seasonal_api_url`) so backend can build history.
- If no merged history is produced from APIs, endpoint returns `404`.

Implementation notes:

- API fetching is split into dedicated modules under `backend/api_calls/`.
- Signal merging and normalization is centralized in `backend/helpers/merge_history.py`.
- The same merged final dataset drives forecasting in `/forecast/api` and pipeline option 1 when `history[]` is omitted.
