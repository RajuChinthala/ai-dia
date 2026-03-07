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

## Optional: ChromaDB install

Chroma memory integration is implemented in code but kept as an optional dependency so base installs work on Windows without C++ toolchain.

Install optional Chroma deps:

```bash
pip install -r requirements-chroma.txt
```

Windows note:

- If install fails with `Microsoft Visual C++ 14.0 or greater is required`, install **Microsoft C++ Build Tools** and retry.
- If you do not install Chroma, the pipeline still runs; memory retrieval/upsert gracefully no-ops.

## Docker (API + ChromaDB + Ollama)

Run the backend and Chroma as containers:

```bash
docker compose up --build
```

Run with Vite dev frontend (hot reload):

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

Services:

- API: `http://localhost:8000`
- Chroma: `http://localhost:8001`
- Ollama: `http://localhost:11434`
- UI: `http://localhost:5173`
- Memory health: `GET http://localhost:8000/pipeline/memory/health`

Notes:

- `api` container is preconfigured with `CHROMA_HOST=chroma` and uses Chroma server mode.
- `ollama` container provides local model inference for API (`LOCAL_LLM_API_BASE=http://ollama:11434`).
- `ollama-init` one-shot service auto-pulls `llama3.2:3b` on startup (via `OLLAMA_HOST=http://ollama:11434`).
- `frontend` container runs in production mode (Vite build + Nginx static serve).
- Nginx proxies `/api` to `api` service inside Docker network.
- `chroma_data` Docker volume persists vector memory.
- `ollama_data` Docker volume persists pulled models.
- Compose defaults for containerized Ollama are tuned for stability: `LLM_TIMEOUT_SEC=150`, `LLM_REQUEST_MAX_SEC=420`, `LLM_MAX_TOKENS=1024`.

Manual model pull (optional, if you want to re-pull/update):

```bash
docker compose exec ollama ollama pull llama3.2:3b
```

Optional check:

```bash
docker compose exec ollama ollama list
```

Optional frontend dev mode (instead of production target):

```bash
docker build -f frontend/Dockerfile --target development -t ai-dia-frontend-dev ./frontend
```

Useful commands:

```bash
docker compose down
docker compose down -v
docker compose restart api
```

- `down` keeps Chroma data volume.
- `down -v` removes persisted Chroma data.

## Notes

- Data model is aligned to **BigCommerce Inventory API**: `product_id`, optional `variant_id`, `location_id`, `inventory_level` (ATS per location), safety stock, capacity, shipping cost, and service level.
- Optimizer combines forecasted demand + safety stock with shipping cost, capacity, and service level to produce allocations. Positive qty = ship in, negative qty = transfer out.
- For production usage, send real merged history rows (`units`, `weather_score`, `social_signal`) through `/pipeline/agent_forecast_allocate`.
- The updated notebook can call `/pipeline/notebook_forecast` to execute and standardize forecast outputs in CSV form.

## Agent orchestration pattern

`POST /pipeline/agent_forecast_allocate` now uses a **RAG pipeline**:

1. Retrieve: query Chroma memory for semantically similar prior runs.
2. Augment: build retrieval context (`retrieved_cases` + retrieval insights) and add it to prompts.
3. Generate: run forecast and allocation LLM stages grounded in retrieved context.

Request highlights:

- Source APIs are resolved from backend configuration (`backend/api_calls/config.py`) when not provided in request.
- Optional override in request: `sales_api_url`, `weather_api_url`, `seasonal_api_url`.
- Optional alias: `social_api_url` (deprecated alias for `seasonal_api_url`).
- Optional: `history[]` to bypass API fetch and directly run RAG stages.
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
- `retrieval_context` contains query metadata, compact retrieved cases, and retrieval summary insights.
- `allocation_mode` remains `llm` for backward compatibility (the flow is retrieval-augmented internally).

This gives you retrieval-grounded forecast and allocation in one endpoint.

## LLM setup

The RAG pipeline uses LLM for generation and Chroma memory for retrieval.

### Required env vars

- `USE_LOCAL_MODEL` (`true`/`false`, default `false`)
- `LLM_API_BASE` (default `https://api.openai.com/v1`)
- `LLM_MODEL` (default `gpt-4o-mini`)
- `LLM_TIMEOUT_SEC` (default `45`, local defaults are higher)
- `LLM_REQUEST_MAX_SEC` (default `75`, local defaults are higher)
- `LLM_RETRY_MAX` (default `3`)
- `LLM_RETRY_BACKOFF_SEC` (default `1.0`)
- `LLM_MAX_TOKENS` (default `512`, local defaults are higher)

### Local Ollama setup

Use these values in `.env` when Ollama is running locally:

- `USE_LOCAL_MODEL=true`
- `LOCAL_LLM_API_BASE=http://localhost:11434`
- `LOCAL_LLM_MODEL=llama3.2:3b`
- `LOCAL_LLM_API_KEY=` (optional)
- `LLM_TIMEOUT_SEC=90`
- `LLM_REQUEST_MAX_SEC=180`
- `LLM_MAX_TOKENS=2048`

For hosted providers (OpenAI), set `USE_LOCAL_MODEL=false` and use:

- `LLM_API_BASE=https://api.openai.com/v1`
- `LLM_MODEL=gpt-4o-mini`
- `LLM_API_KEY=<your_key>` (or `OPENAI_API_KEY`)

### Request behavior

- Provide `history[]` directly, or provide source API URLs so backend can build history.
- If no merged history is produced from APIs, endpoint returns `404`.

### ChromaDB memory (agent flow)

- `ENABLE_CHROMA_MEMORY=true` (default)
- `CHROMA_PERSIST_DIR=data/chroma`
- `CHROMA_COLLECTION=agent_flow_runs`
- `CHROMA_TOP_K=3`
- `CHROMA_HOST` (optional; when set, uses remote Chroma server mode)
- `CHROMA_PORT=8000`
- `CHROMA_SSL=false`

Behavior:

- Pipeline first queries similar prior runs for the same `product_id`; if no records exist, it falls back to broader semantic retrieval.
- Pipeline injects retrieval context into both forecast and allocation prompts.
- Pipeline upserts final run context and outputs into Chroma for future retrieval.

Implementation notes:

- Chroma integration is optional and gracefully no-ops if dependency is unavailable.

If you see timeout errors on first request (model cold start), increase:

- `LLM_REQUEST_MAX_SEC=180`
- `LLM_TIMEOUT_SEC=90`

