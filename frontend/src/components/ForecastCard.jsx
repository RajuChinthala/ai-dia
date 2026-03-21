import React from "react";

export default function ForecastCard({ forecast }) {
  if (!forecast) return null;
  const products = Array.isArray(forecast.products) ? forecast.products : [];
  const productSummary = products
    .slice(0, 3)
    .map((row) => row.product_name || row.sku || row.product_id)
    .join(", ");

  return (
    <div className="forecast-card">
      <div className="meta">
        <div>
          <div className="label">Location</div>
          <div style={{ fontSize: 20, fontWeight: 700 }}>{forecast.location_id}</div>
        </div>
        <div>
          <div className="label">Avg Daily</div>
          <div style={{ fontSize: 20, fontWeight: 700 }}>{forecast.avg_daily}</div>
        </div>
      </div>
      <div style={{ marginTop: 6, fontSize: 12 }} className="muted">
        Product: {forecast.product_id || "N/A"}
      </div>
      {!!products.length && (
        <div style={{ marginTop: 4, fontSize: 12 }} className="muted">
          Products: {productSummary}
          {products.length > 3 ? ` +${products.length - 3} more` : ""}
        </div>
      )}
      <div style={{ marginTop: 8, fontSize: 12 }} className="muted">
        Trend: {forecast.trend_hint} | Seasonality: {forecast.seasonality_hint}
      </div>
      <div style={{ marginTop: 12 }}>
        <div className="label">Next {forecast.horizon} days</div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 6 }}>
          {forecast.forecast.map((row) => (
            <div key={row.date} className="pill">
              <div style={{ fontSize: 11 }}>{row.date}</div>
              <div style={{ fontWeight: 700 }}>{row.expected_units}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
