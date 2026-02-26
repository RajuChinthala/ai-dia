import React, { useMemo, useState } from "react";
import ForecastGrid from "./components/ForecastGrid.jsx";
import AllocationTable from "./components/AllocationTable.jsx";
import LocationsPanel from "./components/LocationsPanel.jsx";
import api from "./api";
import "./styles.css";

const defaultLocations = [
  {
    location_id: 1001,
    location_name: "New York DC",
    inventory_level: 150,
    demand_forecast: 250,
    capacity: 450,
    safety_stock: 60,
    shipping_cost: 3,
    service_level: 0.95,
  },
  {
    location_id: 1002,
    location_name: "Los Angeles Store",
    inventory_level: 280,
    demand_forecast: 180,
    capacity: 400,
    safety_stock: 50,
    shipping_cost: 4.5,
    service_level: 0.9,
  },
  {
    location_id: 1003,
    location_name: "Chicago Store",
    inventory_level: 120,
    demand_forecast: 220,
    capacity: 380,
    safety_stock: 55,
    shipping_cost: 2.5,
    service_level: 0.92,
  },
];

export default function App() {
  const [locations, setLocations] = useState(defaultLocations);
  const [inbound, setInbound] = useState(500);
  const [forecasts, setForecasts] = useState([]);
  const [plan, setPlan] = useState(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [forecastLoading, setForecastLoading] = useState(false);
  const [forecastMessage, setForecastMessage] = useState("");
  const [llmLoading, setLlmLoading] = useState(false);
  const [llmMessage, setLlmMessage] = useState("");

  const productId = "1";

  const summary = useMemo(() => {
    const demand = locations.reduce((acc, s) => acc + s.demand_forecast, 0);
    const onHand = locations.reduce((acc, s) => acc + s.inventory_level, 0);
    return { demand, onHand };
  }, [locations]);

  const updateLocation = (locationId, field, value) => {
    setLocations((prev) =>
      prev.map((s) => (s.location_id === locationId ? { ...s, [field]: value } : s))
    );
  };

  // NOTE: Forecasts should come from the notebook/pipeline endpoint.
  // The previous /sample/forecast helper is intentionally not used to keep parity with notebook inputs.

  const runNotebookForecast = async () => {
    try {
      setForecastLoading(true);
      setForecastMessage("Running notebook...");
      await api.post("/pipeline/notebook_forecast", {});
      setForecastMessage("Notebook complete. Loading forecasts...");
      const res = await api.post("/forecast", { product_id: productId });
      setForecasts(res.data?.forecasts || []);
      const count = res.data?.forecasts?.length ?? 0;
      setForecastMessage(`Forecasts refreshed (${count} locations).`);
    } catch (err) {
      console.error(err);
      const detail = err?.response?.data?.detail;
      setForecastMessage(detail || "Notebook run failed. Check backend logs.");
    } finally {
      setForecastLoading(false);
    }
  };

  const runAllocation = async () => {
    try {
      setLoading(true);
      setMessage("Optimizing allocation...");
      const payload = { product_id: productId, inbound: Number(inbound), locations };
      const res = await api.post("/allocate", payload);
      setPlan(res.data);
      setMessage("Allocation generated");
    } catch (err) {
      console.error(err);
      setMessage("Could not call allocation endpoint - ensure backend is running.");
    } finally {
      setLoading(false);
    }
  };

  const runLlmAllocation = async () => {
    try {
      setLlmLoading(true);
      setLlmMessage("Running LLM allocation...");
      const payload = { product_id: productId, inbound: Number(inbound), locations };
      const res = await api.post("/llm/allocation", payload);
      setPlan(res.data);
      setLlmMessage("LLM allocation generated");
    } catch (err) {
      console.error(err);
      const detail = err?.response?.data?.detail;
      setLlmMessage(detail || "Could not run LLM allocation - check backend/LLM.");
    } finally {
      setLlmLoading(false);
    }
  };

  return (
    <div className="page">
      <div className="header">
        <div>
          <div style={{ color: "#38bdf8", letterSpacing: 1 }}>Dynamic Allocation</div>
          <h1 style={{ margin: 4, fontSize: 28 }}>Demand Forecast + Inventory Optimizer</h1>
          <div className="muted">
            Product {productId}. Align inbound units with BigCommerce locations (ATS per location_id).
          </div>
        </div>
        <div style={{ textAlign: "right", color: "#cbd5e1" }}>
          <div>Demand (7d): {summary.demand}</div>
          <div>On hand: {summary.onHand}</div>
          <div>Inbound: {inbound}</div>
        </div>
      </div>

      <div className="grid-two">
        <div className="panel">
          <LocationsPanel
            locations={locations}
            inbound={inbound}
            setInbound={setInbound}
            updateLocation={updateLocation}
          />
          <button onClick={runAllocation} className="button-primary" disabled={loading}>
            {loading ? "Working..." : "Optimize Allocation"}
          </button>
          <button
            onClick={runLlmAllocation}
            className="button-ghost"
            disabled={llmLoading}
            style={{ marginTop: 10, width: "100%" }}
          >
            {llmLoading ? "Running LLM..." : "Optimize with LLM"}
          </button>
          {message && <div style={{ color: "#cbd5e1", marginTop: 8 }}>{message}</div>}
          {llmMessage && <div style={{ color: "#cbd5e1", marginTop: 6 }}>{llmMessage}</div>}
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div className="panel">
            <div className="panel-header">
              <div style={{ fontWeight: 700 }}>Forecasts</div>
              <div style={{ color: "#94a3b8", fontSize: 12 }}>
                Run the notebook to refresh forecasts from the final CSV output.
              </div>
            </div>
            <button
              className="button-ghost"
              onClick={runNotebookForecast}
              disabled={forecastLoading}
              style={{ marginBottom: 8, width: "100%" }}
            >
              {forecastLoading ? "Running notebook..." : "Run Notebook Forecast"}
            </button>
            {forecastMessage && <div style={{ color: "#cbd5e1", marginTop: 8 }}>{forecastMessage}</div>}
            <ForecastGrid forecasts={forecasts} />
          </div>
          <AllocationTable plan={plan} />
        </div>
      </div>
    </div>
  );
}

// Field moved into LocationsPanel
