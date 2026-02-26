import React from "react";

export default function AllocationTable({ plan }) {
  if (!plan || !plan.allocations) return null;
  return (
    <div className="panel">
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
        <div style={{ fontWeight: 700, fontSize: 16 }}>Allocation Plan</div>
        <div style={{ color: "#cbd5e1", fontSize: 13 }}>
          Fill rate: {plan.fill_rate} | Est. cost: ${plan.estimated_total_cost}
        </div>
      </div>
      <table className="allocation-table">
        <thead>
          <tr>
            <th>Location</th>
            <th>Qty</th>
            <th>Rationale</th>
            <th>Cost</th>
          </tr>
        </thead>
        <tbody>
          {plan.allocations.map((row, idx) => (
            <tr key={idx}>
              <td>{row.location_id}</td>
              <td style={{ color: row.quantity < 0 ? "#f59e0b" : "#22d3ee" }}>{row.quantity}</td>
              <td>{row.rationale}</td>
              <td>${row.estimated_cost?.toFixed(2)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div style={{ fontSize: 12 }} className="muted">
        Inbound remaining: {plan.inbound_remaining}
      </div>
    </div>
  );
}
