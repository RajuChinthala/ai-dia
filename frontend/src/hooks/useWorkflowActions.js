import { useCallback, useState } from "react";
import api from "../api";
import { APP_CONFIG } from "../constants/appConfig.js";

export default function useWorkflowActions({
  productId,
  inbound,
  locations,
  setLocations,
  setForecasts,
  setPlan,
}) {
  const [sampleLoading, setSampleLoading] = useState(false);
  const [sampleMessage, setSampleMessage] = useState("");

  const [forecastLoading, setForecastLoading] = useState(false);
  const [forecastMessage, setForecastMessage] = useState("");

  const [agentLoading, setAgentLoading] = useState(false);
  const [agentMessage, setAgentMessage] = useState("");

  const runNotebookForecast = useCallback(async () => {
    try {
      setForecastLoading(true);
      setForecastMessage("Running notebook...");
      await api.post("/pipeline/notebook_forecast", {});
      setForecastMessage("Notebook complete. Loading forecasts...");
      const response = await api.post("/forecast", { product_id: productId });
      setForecasts(response.data?.forecasts || []);
      const count = response.data?.forecasts?.length ?? 0;
      setForecastMessage(`Forecasts refreshed (${count} locations).`);
    } catch (err) {
      console.error(err);
      const detail = err?.response?.data?.detail;
      setForecastMessage(detail || "Notebook run failed. Check backend logs.");
    } finally {
      setForecastLoading(false);
    }
  }, [productId, setForecasts]);

  const runSampleAllocation = useCallback(async () => {
    try {
      setSampleLoading(true);
      setSampleMessage("Optimizing allocation...");
      const payload = {
        product_id: productId,
        inbound: Number(inbound),
        locations,
      };
      const response = await api.post("/allocate", payload);
      setPlan(response.data);
      setSampleMessage("Allocation generated.");
    } catch (err) {
      console.error(err);
      setSampleMessage(
        "Could not call allocation endpoint. Ensure backend is running.",
      );
    } finally {
      setSampleLoading(false);
    }
  }, [inbound, locations, productId, setPlan]);

  const runAgentPipeline = useCallback(async () => {
    try {
      setAgentLoading(true);
      setAgentMessage("Running agent pipeline...");

      const payload = {
        product_id: productId,
        inbound: Number(inbound),
        locations,
        horizon: APP_CONFIG.agentHorizonDays,
        history: [],
      };

      const response = await api.post(
        "/pipeline/agent_forecast_allocate",
        payload,
      );
      const data = response.data || {};
      setPlan(data);

      const specialist = data.specialist_outputs || [];
      if (specialist.length) {
        const byLocation = Object.fromEntries(
          specialist.map((row) => [row.location_id, row.final_period_forecast]),
        );

        setLocations((prev) =>
          prev.map((location) => ({
            ...location,
            demand_forecast: Number(
              byLocation[location.location_id] ?? location.demand_forecast,
            ),
          })),
        );

        const forecastRows = specialist.map((row) => {
          const daily = Number(row.final_daily_forecast || 0);
          const horizon = APP_CONFIG.agentHorizonDays;
          const start = new Date();
          const forecast = Array.from({ length: horizon }, (_, idx) => {
            const dt = new Date(start);
            dt.setDate(start.getDate() + idx + 1);
            return {
              date: dt.toISOString().slice(0, 10),
              expected_units: Number(daily.toFixed(2)),
            };
          });
          return {
            product_id: productId,
            location_id: row.location_id,
            horizon,
            avg_daily: Number(daily.toFixed(2)),
            trend_hint: Number(row.sales_trend_daily || 0),
            seasonality_hint: Number(row.seasonal_weekly_delta || 0),
            forecast,
          };
        });
        setForecasts(forecastRows);
      }

      setAgentMessage("Agent pipeline completed and allocation generated.");
    } catch (err) {
      console.error(err);
      const detail = err?.response?.data?.detail;
      setAgentMessage(detail || "Agent pipeline failed. Check backend logs.");
    } finally {
      setAgentLoading(false);
    }
  }, [inbound, locations, productId, setForecasts, setLocations, setPlan]);

  return {
    sampleLoading,
    sampleMessage,
    forecastLoading,
    forecastMessage,
    agentLoading,
    agentMessage,
    runNotebookForecast,
    runSampleAllocation,
    runAgentPipeline,
  };
}
