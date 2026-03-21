import React, { useState } from "react";
import ForecastGrid from "../components/ForecastGrid.jsx";
import AllocationTable from "../components/AllocationTable.jsx";
import LocationsPanel from "../components/LocationsPanel.jsx";
import { PAGE_TEXT } from "../constants/pageConfig.js";
import PageHeader from "./PageHeader.jsx";

export default function AgentPage({
  summary,
  inbound,
  productId,
  locations,
  setInbound,
  updateLocation,
  onBack,
  runAgentPipeline,
  agentLoading,
  agentMessage,
  loadLocationsFromBigCommerce,
  bigCommerceLoading,
  bigCommerceMessage,
  forecasts,
  plan,
}) {
  const [productIdsCsv, setProductIdsCsv] = useState("");
  const [locationIdsCsv, setLocationIdsCsv] = useState("");
  const [useSimulation, setUseSimulation] = useState(true);

  return (
    <div className="page">
      <PageHeader
        title={PAGE_TEXT.agent.title}
        subtitle={`${productId ? `Product ${productId}.` : "No product selected."} ${PAGE_TEXT.agent.subtitle}`}
        summary={summary}
        inbound={inbound}
      />
      <button className="button-ghost" onClick={onBack} style={{ marginBottom: 12 }}>
        ← Back to Home
      </button>
      <div className="grid-two">
        <div className="panel">
          <LocationsPanel
            locations={locations}
            inbound={inbound}
            setInbound={setInbound}
            updateLocation={updateLocation}
          />
          <div style={{ marginTop: 8, display: "grid", gap: 8 }}>
            <input
              className="input"
              value={productIdsCsv}
              onChange={(e) => setProductIdsCsv(e.target.value)}
              placeholder="Product IDs (csv, optional): 101,102,103"
            />
            <input
              className="input"
              value={locationIdsCsv}
              onChange={(e) => setLocationIdsCsv(e.target.value)}
              placeholder="Location IDs (csv, optional): 1001,1002"
            />
            <label style={{ color: "#cbd5e1", fontSize: 13, display: "flex", gap: 8, alignItems: "center" }}>
              <input
                type="checkbox"
                checked={useSimulation}
                onChange={(e) => setUseSimulation(e.target.checked)}
              />
              Use simulated multi-location data
            </label>
          </div>
          <button
            onClick={() =>
              loadLocationsFromBigCommerce({
                productIdsCsv,
                locationIdsCsv,
                useSimulation,
              })
            }
            className="button-primary"
            disabled={bigCommerceLoading}
            style={{ marginTop: 8 }}
          >
            {bigCommerceLoading ? "Loading BigCommerce data..." : "Load Locations from BigCommerce"}
          </button>
          <button onClick={runAgentPipeline} className="button-primary" disabled={agentLoading}>
            {agentLoading ? "Running pipeline..." : "Run Agent Pipeline"}
          </button>
          {agentMessage && <div style={{ color: "#cbd5e1", marginTop: 8 }}>{agentMessage}</div>}
          {bigCommerceMessage && (
            <div style={{ color: "#cbd5e1", marginTop: 8 }}>{bigCommerceMessage}</div>
          )}
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div className="panel">
            <div className="panel-header">
              <div style={{ fontWeight: 700 }}>Forecasts</div>
              <div style={{ color: "#94a3b8", fontSize: 12 }}>From agent pipeline specialist outputs</div>
            </div>
            <ForecastGrid forecasts={forecasts} />
          </div>
          <AllocationTable plan={plan} />
        </div>
      </div>
    </div>
  );
}
