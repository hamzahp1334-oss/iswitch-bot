import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from customer_bot.handlers.checkout import parse_order_details_text

class TestUnifiedCheckoutParser(unittest.TestCase):
    def test_multiline_format(self):
        text = "Abebe Kebede\n0911223344\nBole near Edna Mall"
        parsed = parse_order_details_text(text)
        self.assertEqual(parsed.get("phone"), "0911223344")
        self.assertEqual(parsed.get("full_name"), "Abebe Kebede")
        self.assertEqual(parsed.get("address"), "Bole near Edna Mall")

    def test_comma_delimited_format(self):
        text = "Sara Tadesse, 0980632130, CMC Michael, House 45"
        parsed = parse_order_details_text(text)
        self.assertEqual(parsed.get("phone"), "0980632130")
        self.assertEqual(parsed.get("full_name"), "Sara Tadesse")
        self.assertEqual(parsed.get("address"), "CMC Michael, House 45")

    def test_labelled_english_format(self):
        text = (
            "Full Name: Israel Hailu\n"
            "Phone Number: +251912345678\n"
            "Delivery Address: Piassa, Churchill Ave, Floor 3"
        )
        parsed = parse_order_details_text(text)
        self.assertEqual(parsed.get("phone"), "0912345678")
        self.assertEqual(parsed.get("full_name"), "Israel Hailu")
        self.assertEqual(parsed.get("address"), "Piassa, Churchill Ave, Floor 3")

    def test_amharic_labelled_format(self):
        text = (
            "ስም: ዳዊት በቀለ\n"
            "ስልክ: 0970112233\n"
            "አድራሻ: መገናኛ ዘፍመሽ ግራንድ ሞል ፊት ለፊት"
        )
        parsed = parse_order_details_text(text)
        self.assertEqual(parsed.get("phone"), "0970112233")
        self.assertEqual(parsed.get("full_name"), "ዳዊት በቀለ")
        self.assertIn("መገናኛ", parsed.get("address", ""))

    def test_ethio_telecom_07_prefix(self):
        text = "Yonas Alemu, 0712345678, Sarbet Gabon Street"
        parsed = parse_order_details_text(text)
        self.assertEqual(parsed.get("phone"), "0712345678")
        self.assertEqual(parsed.get("full_name"), "Yonas Alemu")
        self.assertEqual(parsed.get("address"), "Sarbet Gabon Street")

    def test_empty_or_whitespace(self):
        parsed = parse_order_details_text("")
        self.assertEqual(parsed, {})
        parsed = parse_order_details_text("   \n  ")
        self.assertEqual(parsed, {})

from unittest.mock import AsyncMock, MagicMock
from database.db import db
from database.crud import seed_initial_data, get_or_create_customer, update_customer_delivery_info
from customer_bot.handlers.checkout import _finalize_order

class TestFinalizeOrderSavedInfo(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await db.init_db()
        await seed_initial_data()

    async def test_finalize_order_with_saved_details(self):
        """Simulates customer uploading receipt when saved delivery info is present."""
        user_id = 99887766
        # Setup customer with saved details (exact scenario from user's screenshot)
        cust = await get_or_create_customer(user_id, username="mrx_test", full_name="Mr.X")
        await update_customer_delivery_info(
            telegram_user_id=user_id,
            full_name="Mr.X",
            phone="+251704039090",
            city="Addis Ababa",
            area="Mezegaja",
            address="halaba kulito addisu mezegaja sefer",
            landmark=""
        )

        # Mock Telegram update and context
        update = MagicMock()
        update.effective_user.id = user_id
        update.effective_user.full_name = "Mr.X"
        update.effective_user.username = "mrx_test"
        update.message.reply_text = AsyncMock()

        context = MagicMock()
        context.user_data = {
            "cart": {
                1: {
                    "product_id": 1,
                    "name": "iPhone 15",
                    "unit_price": 100000.0,
                    "qty": 1
                }
            },
            "checkout": {
                "full_name": "Mr.X",
                "phone": "+251704039090",
                "address": "halaba kulito addisu mezegaja sefer",
                "city": "Addis Ababa",
                "delivery_fee": 150.0
            }
        }
        mock_file = MagicMock()
        mock_file.file_path = "https://example.com/mock.jpg"
        context.bot.get_file = AsyncMock(return_value=mock_file)

        # Execute _finalize_order
        res = await _finalize_order(
            update=update,
            context=context,
            file_id="mock_file_id_123",
            download_file_id="mock_dl_file_id_123",
            original_name="receipt.jpg",
            file_size=1024,
            is_photo=True
        )

        # Verify reply_text was called with 'Your order is under review'
        self.assertTrue(update.message.reply_text.called)
        call_args = update.message.reply_text.call_args[0][0]
        self.assertIn("Your order is under review", call_args)
        self.assertIn("Mr.X", call_args)
        self.assertIn("+251704039090", call_args)

if __name__ == "__main__":
    unittest.main()
