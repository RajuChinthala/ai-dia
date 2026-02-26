# Dynamic Allocation Prototype

AI-driven demand forecasting + inventory allocation demo that mirrors the Dynamic-Allocation brief. It includes:

- **Notebook** clone with new input fields and an embedded optimization run.
- **FastAPI** service exposing `/forecast` and `/allocate` endpoints.
- **React (Vite)** UI to load sample forecasts and run allocations.

## Project layout

- `demand_forecast_prototype.ipynb` – original notebook (unchanged).
- `notebooks/demand_forecast_updated.ipynb` – cloned notebook with product/store fields, inbound units, safety stock, and a call into the optimization engine.
- `backend/` – FastAPI app, lightweight forecaster, allocation optimizer, and sample data generator.
- `frontend/` – React UI wired to the API.
- `requirements.txt` – Python deps (forecasting/ML + API + optimization).

## Execution steps

1) **Python environment**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2) **Run FastAPI service**
```bash
uvicorn backend.app:app --reload --port 8000
```
- Health: `GET http://localhost:8000/health`
- Sample forecast: `GET http://localhost:8000/sample/forecast?horizon=7`
- Sample allocation: `GET http://localhost:8000/sample/allocate`
- Custom forecast: `POST http://localhost:8000/forecast` with history rows
- Custom allocation: `POST http://localhost:8000/allocate` with inbound + locations payload
- Notebook pipeline: `POST http://localhost:8000/pipeline/forecast_allocate` (history → forecasts → allocation in one call)

3) **React UI (Vite)**
```bash
cd frontend
npm install
npm run dev
```
- Opens on `http://localhost:5173`; proxy sends `/api/*` to `http://localhost:8000`.
- Click “Load Sample Forecast” then “Optimize Allocation” to see the flow.

4) **Notebook**
- Open `notebooks/demand_forecast_updated.ipynb` in Jupyter/Lab/VS Code.
- Run the new cells near the top to build extended inputs and call the allocation optimizer.

5) **CLI smoke test (no server)**
```bash
source .venv/bin/activate
python -m backend.app
```
Prints sample forecast + allocation plan using the built-in synthetic data.

## Notes

- Data model is aligned to **BigCommerce Inventory API**: `product_id`, optional `variant_id`, `location_id`, `inventory_level` (ATS per location), safety stock, capacity, shipping cost, and service level.
- Optimizer combines forecasted demand + safety stock with shipping cost, capacity, and service level to produce allocations. Positive qty = ship in, negative qty = transfer out.
- Sample product/locations and synthetic signals live in `backend/sample_data.py`; tweak inbound units, service levels, capacities, or shipping costs to experiment.
- The updated notebook includes a cell that calls the `/pipeline/forecast_allocate` API so notebook data flows through the backend.
