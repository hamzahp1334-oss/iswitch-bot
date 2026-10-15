import unittest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from pathlib import Path
import tempfile
import shutil

from database.db import Database
import database.crud as crud
from services.notifier import NotifierService

class TestPaymentRejection(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_reject.sqlite"
        self.test_db = Database(self.db_path)
        self.orig_db = crud.db
        crud.db = self.test_db
        await self.test_db.init_db()
        await crud.seed_initial_data()

    async def asyncTearDown(self):
        crud.db = self.orig_db
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    async def test_rejection_database_flow(self):
        cats = await crud.get_all_categories()
        cat_id = cats[0]["category_id"] if cats else 1
        pid = await crud.create_product(
            name="iPhone 15 Pro",
            category_id=cat_id,
            price=145000.0,
            stock_quantity=5
        )

        cust = await crud.get_or_create_customer(999888, "testuser", "Abebe B.", "+251911000000")
        items = [{"product_id": pid, "product_name": "iPhone 15 Pro", "unit_price": 145000.0, "quantity": 1}]
        deliv = {"city": "Addis Ababa", "address": "Bole"}
        order = await crud.create_order(cust["customer_id"], items, deliv)

        await crud.verify_payment(order["order_id"], admin_id=742368838, approved=False, reason="Unclear / Blurry Image")

        updated_order = await crud.get_order_by_id(order["order_id"])
        self.assertEqual(updated_order["payment_status"], "Rejected")
        self.assertEqual(updated_order["order_status"], "Payment Pending")
        self.assertEqual(updated_order["payment"]["status"], "Rejected")
        self.assertEqual(updated_order["payment"]["rejection_reason"], "Unclear / Blurry Image")

    async def test_customer_notification_payload(self):
        notifier = NotifierService()
        mock_bot = MagicMock()
        mock_bot.send_message = AsyncMock()

        mock_app = MagicMock()
        mock_app.bot = mock_bot
        notifier.register_bots(mock_app, MagicMock())

        success = await notifier.notify_customer_payment_rejected(
            telegram_user_id=999888,
            order_number="ISW-TEST-001",
            reason="Amount Does Not Match",
            order_id=42
        )

        self.assertTrue(success)
        mock_bot.send_message.assert_called_once()
        call_kwargs = mock_bot.send_message.call_args.kwargs
        self.assertEqual(call_kwargs["chat_id"], 999888)
        self.assertIn("Amount Does Not Match", call_kwargs["text"])
        self.assertIn("Payment Receipt Rejected", call_kwargs["text"])

        # Check inline keyboard has re-upload button
        keyboard = call_kwargs["reply_markup"]
        btn_data = [btn.callback_data for row in keyboard.inline_keyboard for btn in row]
        self.assertIn("ord_upload_rcpt_42", btn_data)
        self.assertIn("ord_view_42", btn_data)

if __name__ == "__main__":
    unittest.main()
