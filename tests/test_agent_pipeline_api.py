import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app import app


def _build_history(product_id: str):
    history = []
    for day in range(1, 31):
        dt = f"2026-01-{day:02d}"
        history.append(
            {
                "date": dt,
                "product_id": product_id,
                "location_id": 2001,
                "units": 42 + (day % 7) * 2,
                "weather_score": 0.15 + (day % 3) * 0.03,
                "social_signal": 0.20 + (day % 5) * 0.04,
                "event_score": 0.1 if day % 10 == 0 else 0.0,
            }
        )
        history.append(
            {
                "date": dt,
                "product_id": product_id,
                "location_id": 2002,
                "units": 36 + (day % 6) * 3,
                "weather_score": 0.10 + (day % 4) * 0.02,
                "social_signal": 0.25 + (day % 4) * 0.03,
                "event_score": 0.15 if day % 12 == 0 else 0.0,
            }
        )
    return history


def _build_locations():
    return [
        {
            "location_id": 2001,
            "location_name": "Bengaluru Hub",
            "inventory_level": 110,
            "demand_forecast": 0,
            "capacity": 500,
            "safety_stock": 40,
            "shipping_cost": 2.8,
            "service_level": 0.95,
        },
        {
            "location_id": 2002,
            "location_name": "Mumbai Store",
            "inventory_level": 160,
            "demand_forecast": 0,
            "capacity": 380,
            "safety_stock": 35,
            "shipping_cost": 3.6,
            "service_level": 0.92,
        },
    ]


class TestAgentPipelineApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    @patch("backend.routes.pipeline.llm_pipeline.run_llm_orchestrated_pipeline")
    @patch("backend.routes.pipeline.build_history_and_forecast_from_apis")
    def test_agent_pipeline_llm_endpoint_success(self, mock_helper, mock_llm_pipeline):
        mock_helper.return_value = {
            "history": _build_history("SKU-9001"),
            "forecasts": [],
        }
        mock_llm_pipeline.return_value = {
            "product_id": "SKU-9001",
            "horizon": 7,
            "allocation_mode": "llm",
            "specialist_outputs": [
                {
                    "location_id": 2001,
                    "sales_base_daily": 50.0,
                    "sales_trend_daily": 1.2,
                    "seasonal_weekly_delta": 0.8,
                    "weather_daily_impact": -0.4,
                    "social_daily_impact": 1.1,
                    "final_daily_forecast": 52.7,
                    "final_period_forecast": 369,
                },
                {
                    "location_id": 2002,
                    "sales_base_daily": 45.0,
                    "sales_trend_daily": 0.9,
                    "seasonal_weekly_delta": 0.6,
                    "weather_daily_impact": -0.2,
                    "social_daily_impact": 0.8,
                    "final_daily_forecast": 47.1,
                    "final_period_forecast": 330,
                },
            ],
            "allocations": [
                {
                    "location_id": 2001,
                    "quantity": 170,
                    "rationale": "LLM allocation",
                    "estimated_cost": 476.0,
                },
                {
                    "location_id": 2002,
                    "quantity": 130,
                    "rationale": "LLM allocation",
                    "estimated_cost": 468.0,
                },
            ],
            "inbound_remaining": 0,
            "estimated_total_cost": 944.0,
            "fill_rate": 0.96,
        }

        payload = {
            "product_id": "SKU-9001",
            "variant_id": 501,
            "inbound": 300,
            "horizon": 7,
            "locations": _build_locations(),
            "history": [],
            "sales_api_url": "https://example.test/sales",
            "weather_api_url": "https://example.test/weather",
            "seasonal_api_url": "https://example.test/seasonal",
        }

        response = self.client.post("/pipeline/agent_forecast_allocate", json=payload)
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertEqual(data["product_id"], "SKU-9001")
        self.assertEqual(data["variant_id"], 501)
        self.assertEqual(data["allocation_mode"], "llm")
        self.assertEqual(len(data["specialist_outputs"]), 2)
        self.assertIn("allocations", data)
        self.assertIn("fill_rate", data)
        mock_helper.assert_called_once()
        mock_llm_pipeline.assert_called_once()

    @patch("backend.routes.pipeline.llm_pipeline.run_llm_orchestrated_pipeline")
    def test_agent_pipeline_uses_history_without_fetch(self, mock_llm_pipeline):
        mock_llm_pipeline.return_value = {
            "product_id": "SKU-9001",
            "horizon": 7,
            "allocation_mode": "llm",
            "specialist_outputs": [],
            "allocations": [],
            "inbound_remaining": 300,nnnnn 
            "estimated_total_cost": 0.0,
            "fill_rate": 0.0,
        }

        payload = {
            "product_id": "SKU-9001",
            "variant_id": 501,
            "inbound": 300,
            "horizon": 7,
            "locations": _build_locations(),
            "history": _build_history("SKU-9001"),
            "sales_api_url": "https://example.test/sales",
            "weather_api_url": "https://example.test/weather",
            "seasonal_api_url": "https://example.test/seasonal",
        }

        with patch("backend.routes.pipeline.build_history_and_forecast_from_apis") as mock_helper:
            response = self.client.post("/pipeline/agent_forecast_allocate", json=payload)
            self.assertEqual(response.status_code, 200)
            mock_helper.assert_not_called()
            mock_llm_pipeline.assert_called_once()

    @patch("backend.routes.forecast.build_history_and_forecast_from_apis")
    def test_forecast_api_endpoint_from_source_apis(
        self,
        mock_helper,
    ):
        mock_helper.return_value = {
            "history": [
                {
                    "date": "2026-01-01",
                    "product_id": "SKU-9001",
                    "location_id": 2001,
                    "units": 52,
                    "weather_score": 0.4,
                    "social_signal": 0.1,
                    "event_score": 0.0,
                }
            ],
            "forecasts": [
                SimpleNamespace(
                    product_id="SKU-9001",
                    location_id=2001,
                    horizon=3,
                    avg_daily=50.0,
                    trend_hint=0.5,
                    seasonality_hint=0.2,
                    forecast=150.0,
                    period_forecast=150.0,
                )
            ],
        }

        payload = {
            "product_id": "SKU-9001",
            "location_ids": [2001],
            "sales_api_url": "https://example.test/sales",
            "weather_api_url": "https://example.test/weather",
            "social_api_url": "https://example.test/social",
            "horizon": 3,
        }

        response = self.client.post("/forecast/api", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("forecasts", data)
        self.assertTrue(len(data["forecasts"]) >= 1)

    @patch("backend.routes.pipeline.llm_pipeline.run_llm_orchestrated_pipeline")
    @patch("backend.routes.pipeline.build_history_and_forecast_from_apis")
    def test_agent_pipeline_llm_error_returns_500(self, mock_helper, mock_llm_pipeline):
        mock_helper.return_value = {
            "history": _build_history("SKU-9001"),
            "forecasts": [],
        }
        mock_llm_pipeline.side_effect = RuntimeError("mock llm unavailable")

        payload = {
            "product_id": "SKU-9001",
            "variant_id": 501,
            "inbound": 300,
            "horizon": 7,
            "locations": _build_locations(),
            "history": [],
            "sales_api_url": "https://example.test/sales",
            "weather_api_url": "https://example.test/weather",
            "seasonal_api_url": "https://example.test/seasonal",
        }

        response = self.client.post("/pipeline/agent_forecast_allocate", json=payload)
        self.assertEqual(response.status_code, 500)


if __name__ == "__main__":
    unittest.main()
