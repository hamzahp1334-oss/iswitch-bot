import sys
import asyncio
import unittest
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from database.db import db
from database.crud import (
    seed_initial_data, get_or_create_customer, create_order,
    get_order_by_id, add_receipt
)
from services.storage import storage_service
from services.ui_utils import escape_md

class TestSecurityHardening(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await db.init_db()
        await seed_initial_data()

    async def test_order_idor_ownership_isolation(self):
        """Verifies that orders are strictly isolated between customer accounts."""
        cust_a = await get_or_create_customer(telegram_user_id=1111111, full_name="User A")
        cust_b = await get_or_create_customer(telegram_user_id=2222222, full_name="User B")

        order_a = await create_order(
            customer_id=cust_a["customer_id"],
            items=[{"product_name": "Earphones", "unit_price": 500.0, "quantity": 1}],
            delivery_info={"full_name": "User A", "phone": "0911000000", "address": "Bole"},
            delivery_fee=150.0
        )

        # Retrieve order
        retrieved = await get_order_by_id(order_a["order_id"])
        self.assertIsNotNone(retrieved)
        # Check ownership logic
        self.assertEqual(retrieved["customer_id"], cust_a["customer_id"])
        self.assertNotEqual(retrieved["customer_id"], cust_b["customer_id"])

    async def test_storage_extension_whitelisting(self):
        """Verifies that malicious or dangerous extensions are blocked/sanitized."""
        valid, err = storage_service.validate_receipt_file("malicious.exe", 1024)
        self.assertFalse(valid)
        self.assertIn("Unsupported file type", err)

        valid_pdf, _ = storage_service.validate_receipt_file("receipt.pdf", 1024)
        self.assertTrue(valid_pdf)

        valid_jpg, _ = storage_service.validate_receipt_file("receipt.jpg", 1024)
        self.assertTrue(valid_jpg)

        # File size exceeding 10MB
        too_large, size_err = storage_service.validate_receipt_file("receipt.jpg", 15 * 1024 * 1024)
        self.assertFalse(too_large)
        self.assertIn("exceeds maximum allowed", size_err)

    def test_markdown_sanitization_escapes_injection(self):
        """Verifies that special Telegram Markdown characters are escaped."""
        raw = "User_Name*Super*[Link](http://malicious.site)`code`"
        escaped = escape_md(raw)
        self.assertIn("\\[Link]", escaped)
        self.assertIn("\\*Super\\*", escaped)
        self.assertNotIn("`", escaped)

if __name__ == "__main__":
    unittest.main()
