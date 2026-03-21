import { useCallback, useState } from "react";
import api from "../api";
import { APP_CONFIG } from "../constants/appConfig.js";

function toLocationRowsFromProducts(products = []) {
  const byLocation = new Map();

  products.forEach((product) => {
    const productId = Number(product?.product_id || 0);
    const variantId = product?.variant_id ?? null;
    const productName = String(product?.product_name || "");
    const sku = String(product?.sku || "");

    (product?.locations || []).forEach((loc) => {
      const locationId = Number(loc?.location_id || 0);
      if (!locationId) {
        return;
      }

      if (!byLocation.has(locationId)) {
        byLocation.set(locationId, {
          location_id: locationId,
          location_name: String(loc?.location_name || `Location ${locationId}`),
          inventory_level: 0,
          demand_forecast: 0,
          capacity: Number(loc?.capacity ?? 500),
          safety_stock: Number(loc?.safety_stock ?? 50),
          shipping_cost: Number(loc?.shipping_cost ?? 3.0),
          service_level: Number(loc?.service_level ?? 0.9),
          products: [],
        });
      }

      const current = byLocation.get(locationId);
      const inventoryLevel = Number(loc?.inventory_level ?? 0);
      current.inventory_level += inventoryLevel;
      current.products.push({
        product_id: productId,
        variant_id: variantId,
        sku,
        product_name: productName,
        availability: String(loc?.availability || "unknown"),
        inventory_level: inventoryLevel,
      });
    });
  });

  return Array.from(byLocation.values()).sort(
    (a, b) => a.location_id - b.location_id,
  );
}

export default function useWorkflowActions({
  productId,
  setProductId,
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

  const [bigCommerceLoading, setBigCommerceLoading] = useState(false);
  const [bigCommerceMessage, setBigCommerceMessage] = useState("");

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

      const productIdsFromLocations = Array.from(
        new Set(
          locations
            .flatMap((location) =>
              Array.isArray(location.products) ? location.products : [],
            )
            .map((product) => Number(product?.product_id || 0))
            .filter((id) => id > 0),
        ),
      );

      const productIdsCsv = productIdsFromLocations.join(",");
      const salesApiOverride = productIdsCsv
        ? `builtin://sales?days=14&seed=42&product_ids=${productIdsCsv}`
        : undefined;

      const payload = {
        product_id: productId,
        inbound: Number(inbound),
        locations,
        horizon: APP_CONFIG.agentHorizonDays,
        history: [],
        sales_api_url: salesApiOverride,
      };

      const response = await api.post(
        "/pipeline/agent_forecast_allocate",
        payload,
      );
      const data = response.data || {};
      setPlan(data);

      const retrievalWarnings = Array.isArray(data?.retrieval_context?.warnings)
        ? data.retrieval_context.warnings.filter(Boolean)
        : [];

      const specialist = data.specialist_outputs || [];
      if (specialist.length) {
        const locationProducts = Object.fromEntries(
          locations.map((location) => [
            location.location_id,
            Array.isArray(location.products) ? location.products : [],
          ]),
        );

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
            product_id: String(productId || data.product_id || ""),
            products: locationProducts[row.location_id] || [],
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

      const historySource = String(data?.history_source || "default");
      const successMessage = `Agent pipeline completed and allocation generated. History source: ${historySource}.`;
      setAgentMessage(
        retrievalWarnings.length
          ? `${successMessage} Warning: ${retrievalWarnings.join(" | ")}`
          : successMessage,
      );
    } catch (err) {
      console.error(err);
      const detail = err?.response?.data?.detail;
      setAgentMessage(detail || "Agent pipeline failed. Check backend logs.");
    } finally {
      setAgentLoading(false);
    }
  }, [inbound, locations, productId, setForecasts, setLocations, setPlan]);

  const loadLocationsFromBigCommerce = useCallback(
    async ({
      productIdsCsv = "",
      locationIdsCsv = "",
      useSimulation = false,
    } = {}) => {
      try {
        setBigCommerceLoading(true);
        setBigCommerceMessage("Loading locations from BigCommerce...");

        const productIds = String(productIdsCsv || "").trim();
        const locationIds = String(locationIdsCsv || "").trim();

        const params = {
          include_csv_data: true,
          products_per_location: 0,
          max_pages: 100,
        };
        if (useSimulation) {
          params.location_products_csv_path =
            "notebooks/location_products_simulated.csv";
        }
        if (locationIds) {
          params.location_ids = locationIds;
        }

        // If product filter is not provided, load all products and aggregate by location for UI editing.
        if (!productIds) {
          const response = await api.get(
            "/pipeline/bigcommerce/products_locations",
            {
              params,
            },
          );

          const products = response?.data?.products || [];
          const nextLocations = toLocationRowsFromProducts(products);

          if (!nextLocations.length) {
            setBigCommerceMessage(
              "No BigCommerce product/location rows found for the provided filters.",
            );
            return;
          }

          setLocations(nextLocations);
          if (typeof setProductId === "function" && products.length) {
            setProductId(String(products[0]?.product_id || ""));
          }

          setBigCommerceMessage(
            `Loaded ${products.length} products across ${nextLocations.length} locations from BigCommerce${useSimulation ? " (simulation mode)" : ""}.`,
          );
          return;
        }

        params.product_ids = productIds;

        const response = await api.get(
          "/pipeline/bigcommerce/allocation_payload",
          {
            params: {
              ...params,
              product_id: Number(productId) || undefined,
              inbound: Number(inbound) || 0,
            },
          },
        );

        const allocationPayload = response?.data?.allocation_payload;
        const selectedProduct = response?.data?.selected_product;
        const nextLocations = (allocationPayload?.locations || []).map(
          (location) => ({
            ...location,
            products: selectedProduct
              ? [
                  {
                    product_id: Number(selectedProduct?.product_id || 0),
                    variant_id: selectedProduct?.variant_id ?? null,
                    sku: String(selectedProduct?.sku || ""),
                    product_name: String(selectedProduct?.product_name || ""),
                    availability: "available",
                    inventory_level: Number(location?.inventory_level || 0),
                  },
                ]
              : [],
          }),
        );

        if (!nextLocations.length) {
          setBigCommerceMessage(
            "No BigCommerce allocation rows found for the provided filters.",
          );
          return;
        }

        setLocations(nextLocations);
        if (typeof setProductId === "function") {
          const selectedProductId =
            selectedProduct?.product_id ?? allocationPayload?.product_id;
          if (selectedProductId != null) {
            setProductId(String(selectedProductId));
          }
        }
        setBigCommerceMessage(
          `Loaded ${nextLocations.length} locations for product ${selectedProduct?.product_id ?? allocationPayload?.product_id} from BigCommerce${useSimulation ? " (simulation mode)" : ""}.`,
        );
      } catch (err) {
        console.error(err);
        const detail = err?.response?.data?.detail;
        setBigCommerceMessage(
          detail || "Failed to load locations from BigCommerce.",
        );
      } finally {
        setBigCommerceLoading(false);
      }
    },
    [inbound, productId, setLocations, setProductId],
  );

  return {
    sampleLoading,
    sampleMessage,
    forecastLoading,
    forecastMessage,
    agentLoading,
    agentMessage,
    bigCommerceLoading,
    bigCommerceMessage,
    runNotebookForecast,
    runSampleAllocation,
    runAgentPipeline,
    loadLocationsFromBigCommerce,
  };
}
