import React from "react";
import ForecastGrid from "../components/ForecastGrid.jsx";
import AllocationTable from "../components/AllocationTable.jsx";
import LocationsPanel from "../components/LocationsPanel.jsx";
import { PAGE_TEXT } from "../constants/pageConfig.js";
import PageHeader from "./PageHeader.jsx";

export default function SamplePage({
  summary,
  inbound,
  productId,
  locations,
  setInbound,
  updateLocation,
  onBack,
  runSampleAllocation,
  sampleLoading,
  sampleMessage,
  runNotebookForecast,
  forecastLoading,
  forecastMessage,
  forecasts,
  plan,
}) {
  return (
    <div className="page">
      <PageHeader
        title={PAGE_TEXT.sample.title}
        subtitle={`Product ${productId}. ${PAGE_TEXT.sample.subtitle}`}
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
          <button onClick={runSampleAllocation} className="button-primary" disabled={sampleLoading}>
            {sampleLoading ? "Working..." : "Optimize Allocation"}
          </button>
          {sampleMessage && <div style={{ color: "#cbd5e1", marginTop: 8 }}>{sampleMessage}</div>}
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div className="panel">
            <div className="panel-header">
              <div style={{ fontWeight: 700 }}>Forecasts</div>
              <div style={{ color: "#94a3b8", fontSize: 12 }}>Notebook-driven forecast refresh</div>
            </div>
            <button
              className="button-ghost"
              onClick={runNotebookForecast}
              disabled={forecastLoading}
              style={{ marginBottom: 8, width: "100%" }}
            >
              {forecastLoading ? "Running notebook..." : "Run Notebook Forecast"}
            </button>
            {forecastMessage && (
              <div style={{ color: "#cbd5e1", marginTop: 8, marginBottom: 8 }}>{forecastMessage}</div>
            )}
            <ForecastGrid forecasts={forecasts} />
          </div>
          <AllocationTable plan={plan} />
        </div>
      </div>
    </div>
  );
}
