import unittest
from unittest.mock import patch

from backend import schemas
from backend.routes.pipeline import agent_forecast_allocate


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
        history.append(
            {
                "date": dt,
                "product_id": product_id,
                "location_id": 2003,
                "units": 40 + (day % 5) * 2,
                "weather_score": 0.18 + (day % 2) * 0.04,
                "social_signal": 0.22 + (day % 6) * 0.03,
                "event_score": 0.2 if day % 9 == 0 else 0.0,
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
        {
            "location_id": 2003,
            "location_name": "Delhi Store",
            "inventory_level": 90,
            "demand_forecast": 0,
            "capacity": 360,
            "safety_stock": 30,
            "shipping_cost": 3.1,
            "service_level": 0.94,
        },
    ]


class TestAgentPipelineFlow(unittest.TestCase):
    @patch("backend.routes.pipeline.llm_pipeline.run_llm_orchestrated_pipeline")
    @patch("backend.routes.pipeline.build_history_and_forecast_from_apis")
    def test_llm_flow_end_to_end(self, mock_helper, mock_llm_pipeline):
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
                }
            ],
            "allocations": [
                {
                    "location_id": 2001,
                    "quantity": 120,
                    "rationale": "LLM allocation",
                    "estimated_cost": 336.0,
                }
            ],
            "inbound_remaining": 300,
            "estimated_total_cost": 336.0,
            "fill_rate": 0.72,
        }

        req = schemas.AgentPipelineRequest(
            product_id="SKU-9001",
            variant_id=501,
            inbound=420,
            horizon=7,
            locations=_build_locations(),
            history=[],
            sales_api_url="https://example.test/sales",
            weather_api_url="https://example.test/weather",
            seasonal_api_url="https://example.test/seasonal",
        )

        result = agent_forecast_allocate(req)

        self.assertEqual(result["product_id"], "SKU-9001")
        self.assertEqual(result["variant_id"], 501)
        self.assertEqual(result["horizon"], 7)
        self.assertEqual(result["allocation_mode"], "llm")
        self.assertGreaterEqual(len(result["specialist_outputs"]), 1)
        self.assertGreaterEqual(result["fill_rate"], 0.0)
        self.assertLessEqual(result["fill_rate"], 1.0)
        self.assertIn("estimated_total_cost", result)
        self.assertIn("allocations", result)

        for row in result["specialist_outputs"]:
            self.assertIn("location_id", row)
            self.assertIn("final_daily_forecast", row)
            self.assertIn("final_period_forecast", row)


if __name__ == "__main__":
    unittest.main()
