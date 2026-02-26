import React from "react";

const Field = ({ label, value, onChange }) => (
  <label className="label-strong" style={{ flex: 1 }}>
    {label}
    <input
      type="number"
      value={value}
      onChange={(e) => onChange(Number(e.target.value))}
      className="input"
    />
  </label>
);

export default function LocationsPanel({ locations, inbound, setInbound, updateLocation }) {
  return (
    <div className="panel">
      <div className="panel-header">
        <div style={{ fontWeight: 700 }}>Inventory Inputs</div>
        <div className="muted" style={{ fontSize: 12 }}>
          Forecasts: use notebook or /pipeline/forecast_allocate output.
        </div>
      </div>
      <div style={{ display: "grid", gap: 12 }}>
        <label className="label-strong">
          Inbound from DC
          <input
            type="number"
            value={inbound}
            onChange={(e) => setInbound(Number(e.target.value))}
            className="input"
          />
        </label>
        {locations.map((location) => (
          <div key={location.location_id} className="location-card">
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <div>
                <div className="label">{location.location_name}</div>
                <div style={{ fontWeight: 700 }}>Location {location.location_id}</div>
              </div>
              <div style={{ color: "#94a3b8", fontSize: 12 }}>
                Service {location.service_level} | Ship ${location.shipping_cost}
              </div>
            </div>
            <div className="field-row">
              <Field
                name="inventory_level"
                label="Inventory level"
                value={location.inventory_level}
                onChange={(val) => updateLocation(location.location_id, "inventory_level", val)}
              />
              <Field
                name="demand_forecast"
                label="Demand (7d)"
                value={location.demand_forecast}
                onChange={(val) => updateLocation(location.location_id, "demand_forecast", val)}
              />
              <Field
                name="capacity"
                label="Capacity"
                value={location.capacity}
                onChange={(val) => updateLocation(location.location_id, "capacity", val)}
              />
              <Field
                name="safety_stock"
                label="Safety"
                value={location.safety_stock}
                onChange={(val) => updateLocation(location.location_id, "safety_stock", val)}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
