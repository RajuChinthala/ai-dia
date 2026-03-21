import unittest

from backend.llm_pipeline import _sanitize_allocations


class TestLlmAllocationSanitize(unittest.TestCase):
    def test_scales_positive_allocations_to_inbound(self):
        result = _sanitize_allocations(
            llm_result={
                "allocations": [
                    {"location_id": 1, "quantity": 500, "rationale": "A", "estimated_cost": 0},
                    {"location_id": 1001, "quantity": 500, "rationale": "B", "estimated_cost": 0},
                    {"location_id": 1002, "quantity": 500, "rationale": "C", "estimated_cost": 0},
                    {"location_id": 1003, "quantity": 500, "rationale": "D", "estimated_cost": 0},
                ],
                "fill_rate": 1,
            },
            locations=[
                {"location_id": 1, "shipping_cost": 3.0},
                {"location_id": 1001, "shipping_cost": 2.8},
                {"location_id": 1002, "shipping_cost": 3.6},
                {"location_id": 1003, "shipping_cost": 3.2},
            ],
            inbound=500,
            product_id="113",
        )

        allocations = result["allocations"]
        self.assertEqual(len(allocations), 4)
        self.assertEqual(sum(max(0, int(x["quantity"])) for x in allocations), 500)
        self.assertEqual(result["inbound_remaining"], 0)

        quantities = sorted(int(x["quantity"]) for x in allocations)
        self.assertEqual(quantities, [125, 125, 125, 125])


if __name__ == "__main__":
    unittest.main()
