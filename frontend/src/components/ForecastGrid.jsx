import React from "react";
import ForecastCard from "./ForecastCard.jsx";

export default function ForecastGrid({ forecasts }) {
  if (!forecasts || !forecasts.length) {
    return <div className="muted">Run the forecast + allocation API to populate forecasts.</div>;
  }
  return (
    <div className="forecast-grid">
      {forecasts.map((f) => (
        <ForecastCard key={f.location_id} forecast={f} />
      ))}
    </div>
  );
}
