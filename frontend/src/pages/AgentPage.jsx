import React from "react";
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
  forecasts,
  plan,
}) {
  return (
    <div className="page">
      <PageHeader
        title={PAGE_TEXT.agent.title}
        subtitle={`Product ${productId}. ${PAGE_TEXT.agent.subtitle}`}
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
          <button onClick={runAgentPipeline} className="button-primary" disabled={agentLoading}>
            {agentLoading ? "Running pipeline..." : "Run Agent Pipeline"}
          </button>
          {agentMessage && <div style={{ color: "#cbd5e1", marginTop: 8 }}>{agentMessage}</div>}
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
