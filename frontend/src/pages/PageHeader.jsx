import React from "react";

export default function PageHeader({ title, subtitle, summary, inbound }) {
  return (
    <div className="header">
      <div>
        <div style={{ color: "#38bdf8", letterSpacing: 1 }}>Dynamic Allocation</div>
        <h1 style={{ margin: 4, fontSize: 28 }}>{title}</h1>
        <div className="muted">{subtitle}</div>
      </div>
      <div style={{ textAlign: "right", color: "#cbd5e1" }}>
        <div>Demand (7d): {summary.demand}</div>
        <div>On hand: {summary.onHand}</div>
        <div>Inbound: {inbound}</div>
      </div>
    </div>
  );
}
