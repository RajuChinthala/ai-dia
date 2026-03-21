import os
import tempfile
import unittest
from pathlib import Path

from backend.api_calls.bigcommerce_inventory import _merge_csv_products_with_bigcommerce, _read_location_products_csv_rows


class TestBigCommerceInventoryCsvMerge(unittest.TestCase):
    def test_merge_adds_csv_location_when_bigcommerce_has_single_location(self):
        bigcommerce_products = [
            {
                "product_id": 101,
                "variant_id": None,
                "sku": "SKU-101",
                "product_name": "Sample Product 101",
                "total_inventory_level": 120,
                "locations": [
                    {
                        "location_id": 2001,
                        "location_name": "Bengaluru Hub",
                        "inventory_level": 120,
                        "availability": "available",
                        "capacity": 500,
                        "safety_stock": 50,
                        "shipping_cost": 3.0,
                        "service_level": 0.9,
                    }
                ],
            }
        ]
        csv_rows = [
            {
                "product_id": 101,
                "variant_id": None,
                "sku": "SKU-101",
                "product_name": "Sample Product 101",
                "location": {
                    "location_id": 2002,
                    "location_name": "Mumbai Store",
                    "inventory_level": 80,
                    "availability": "available",
                    "capacity": 450,
                    "safety_stock": 40,
                    "shipping_cost": 3.8,
                    "service_level": 0.92,
                },
            }
        ]

        merged = _merge_csv_products_with_bigcommerce(bigcommerce_products, csv_rows)

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["product_id"], 101)
        self.assertEqual(len(merged[0]["locations"]), 2)
        self.assertEqual(merged[0]["total_inventory_level"], 200)

    def test_read_csv_parses_canonical_columns(self):
        fd, path = tempfile.mkstemp(suffix=".csv")
        os.close(fd)
        try:
            with open(path, "w", encoding="utf-8", newline="") as fh:
                fh.write(
                    "product_id,variant_id,sku,product_name,location_id,location_name,inventory_level,availability,capacity,safety_stock,shipping_cost,service_level\n"
                )
                fh.write("201,,SKU-201,Product 201,3001,Pune Hub,55,available,400,35,2.5,0.93\n")

            rows = _read_location_products_csv_rows(Path(path))

            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["product_id"], 201)
            self.assertIsNone(rows[0]["variant_id"])
            self.assertEqual(rows[0]["location"]["location_id"], 3001)
            self.assertEqual(rows[0]["location"]["inventory_level"], 55)
        finally:
            if os.path.exists(path):
                os.remove(path)


if __name__ == "__main__":
    unittest.main()
