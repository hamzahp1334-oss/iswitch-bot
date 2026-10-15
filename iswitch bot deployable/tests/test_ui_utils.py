import asyncio
import sys
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, MagicMock

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from telegram import Update, Message, CallbackQuery, Chat, User
from telegram.error import BadRequest
from services.ui_utils import safe_edit_or_send, safe_edit_caption_or_send

class TestUIUtils(unittest.IsolatedAsyncioTestCase):
    async def test_text_message_edit(self):
        # When message has NO photo, edit_message_text should be called
        query = MagicMock(spec=CallbackQuery)
        query.answer = AsyncMock()
        query.edit_message_text = AsyncMock()

        message = MagicMock(spec=Message)
        message.photo = []
        message.document = None
        message.video = None
        message.audio = None
        message.voice = None
        message.sticker = None
        query.message = message

        chat = MagicMock(spec=Chat)
        chat.id = 12345

        update = MagicMock(spec=Update)
        update.callback_query = query
        update.effective_chat = chat

        context = MagicMock()
        context.bot.send_message = AsyncMock()

        await safe_edit_or_send(update, context, "Hello World")
        query.edit_message_text.assert_called_once()
        context.bot.send_message.assert_not_called()

    async def test_photo_message_falls_back_to_send(self):
        # When message HAS a photo, edit_message_text would raise BadRequest.
        # safe_edit_or_send should NEVER call edit_message_text and instead send_message!
        query = MagicMock(spec=CallbackQuery)
        query.answer = AsyncMock()
        query.edit_message_text = AsyncMock()

        message = MagicMock(spec=Message)
        message.photo = [MagicMock()] # Has photo!
        query.message = message

        chat = MagicMock(spec=Chat)
        chat.id = 12345

        update = MagicMock(spec=Update)
        update.callback_query = query
        update.effective_chat = chat

        context = MagicMock()
        context.bot.send_message = AsyncMock()

        await safe_edit_or_send(update, context, "Hello World")
        query.edit_message_text.assert_not_called()
        context.bot.send_message.assert_called_once()

    async def test_caption_edit_on_photo_message(self):
        # When message has photo, safe_edit_caption_or_send should edit caption
        query = MagicMock(spec=CallbackQuery)
        query.answer = AsyncMock()
        query.edit_message_caption = AsyncMock()

        message = MagicMock(spec=Message)
        message.photo = [MagicMock()] # Has photo!
        message.document = None
        message.video = None
        query.message = message

        chat = MagicMock(spec=Chat)
        chat.id = 12345

        update = MagicMock(spec=Update)
        update.callback_query = query
        update.effective_chat = chat

        context = MagicMock()
        context.bot.send_message = AsyncMock()

        await safe_edit_caption_or_send(update, context, "Order Caption")
        query.edit_message_caption.assert_called_once()
        context.bot.send_message.assert_not_called()

    async def test_caption_edit_falls_back_if_caption_too_long(self):
        # Caption > 1024 chars on photo message should send new message
        query = MagicMock(spec=CallbackQuery)
        query.answer = AsyncMock()
        query.edit_message_caption = AsyncMock()

        message = MagicMock(spec=Message)
        message.photo = [MagicMock()]
        query.message = message

        chat = MagicMock(spec=Chat)
        chat.id = 12345

        update = MagicMock(spec=Update)
        update.callback_query = query
        update.effective_chat = chat

        context = MagicMock()
        context.bot.send_message = AsyncMock()

        long_caption = "A" * 1500
        await safe_edit_caption_or_send(update, context, long_caption)
        query.edit_message_caption.assert_not_called()
        context.bot.send_message.assert_called_once()

    def test_format_admin_order_card(self):
        from services.ui_utils import format_admin_order_card
        sample_order = {
            "order_number": "ISW-260928-1391",
            "delivery_name": "Israel",
            "delivery_phone": "0980632130",
            "telegram_username": "israeltester",
            "delivery_city": "Addis Ababa",
            "delivery_area": "Bole",
            "delivery_landmark": "Edna Mall",
            "items": [
                {"product_name": "iPhone 15 Pro Max", "quantity": 1, "total_price": 120000.0}
            ],
            "total": 120150.0,
            "currency": "ETB",
            "delivery_fee": 150.0,
            "payment_method": "Telebirr",
            "payment_status": "Uploaded",
            "order_status": "Payment Pending"
        }
        card = format_admin_order_card(sample_order, title="ORDER")
        self.assertIn("ISW-260928-1391", card)
        self.assertIn("Israel", card)
        self.assertIn("`0980632130`", card)
        self.assertIn("@israeltester", card)
        self.assertIn("Addis Ababa, Bole", card)
        self.assertIn("Edna Mall", card)
        self.assertIn("iPhone 15 Pro Max", card)
        self.assertIn("120,150 ETB", card)
        self.assertIn("💳 Payment Pending", card)

    def test_admin_order_detail_keyboard_stages(self):
        from admin_bot.keyboards import admin_order_detail_keyboard
        # Stage 1: Payment Pending -> Row 1 has Approve & Reject
        ord_pending = {"order_id": 1, "order_status": "Payment Pending", "payment_status": "Uploaded"}
        kb1 = admin_order_detail_keyboard(ord_pending)
        self.assertEqual(len(kb1.inline_keyboard), 3)
        self.assertEqual(kb1.inline_keyboard[0][0].text, "✅ Approve Payment")
        self.assertEqual(kb1.inline_keyboard[0][1].text, "❌ Reject Payment")

        # Stage 2: Payment Confirmed -> Row 1 has Preparing & Out for Delivery
        ord_confirmed = {"order_id": 1, "order_status": "Payment Confirmed", "payment_status": "Verified"}
        kb2 = admin_order_detail_keyboard(ord_confirmed)
        self.assertEqual(len(kb2.inline_keyboard), 3)
        self.assertEqual(kb2.inline_keyboard[0][0].text, "📦 Mark Preparing")
        self.assertEqual(kb2.inline_keyboard[0][1].text, "🚚 Out for Delivery")

        # Stage 3: Preparing -> Row 1 has Out for Delivery & Delivered
        ord_preparing = {"order_id": 1, "order_status": "Preparing", "payment_status": "Verified"}
        kb3 = admin_order_detail_keyboard(ord_preparing)
        self.assertEqual(len(kb3.inline_keyboard), 3)
        self.assertEqual(kb3.inline_keyboard[0][0].text, "🚚 Out for Delivery")
        self.assertEqual(kb3.inline_keyboard[0][1].text, "🎉 Mark Delivered")

        # Stage 4: Out for Delivery -> Row 1 has Delivered & Cancel
        ord_out = {"order_id": 1, "order_status": "Out for Delivery", "payment_status": "Verified"}
        kb4 = admin_order_detail_keyboard(ord_out)
        self.assertEqual(len(kb4.inline_keyboard), 3)
        self.assertEqual(kb4.inline_keyboard[0][0].text, "🎉 Mark Delivered")
        self.assertEqual(kb4.inline_keyboard[0][1].text, "❌ Cancel Order")

    def test_escape_md_and_special_chars(self):
        from services.ui_utils import escape_md, format_admin_order_card
        self.assertEqual(escape_md("Abebe_Bikila*Gold*[1]"), "Abebe\\_Bikila\\*Gold\\*\\[1]")
        
        malicious_order = {
            "order_number": "ISW-TEST-1",
            "delivery_name": "Hacker_Name*VIP*",
            "delivery_phone": "`0911223344`",
            "telegram_username": "user_with_underscores",
            "delivery_city": "Bole",
            "delivery_area": "Area_51",
            "delivery_landmark": "[Near Embassy]",
            "items": [
                {"product_name": "iPhone 15_Pro *Max*", "quantity": 1, "total_price": 1000.0}
            ],
            "total": 1150.0,
            "currency": "ETB",
            "delivery_fee": 150.0,
            "admin_notes": "Note with _underscores_ and *stars*"
        }
        card = format_admin_order_card(malicious_order)
        self.assertIn("Hacker\\_Name\\*VIP\\*", card)
        self.assertIn("@user\\_with\\_underscores", card)
        self.assertIn("Area\\_51", card)
        self.assertIn("\\[Near Embassy]", card)
        self.assertIn("iPhone 15\\_Pro \\*Max\\*", card)
        self.assertIn("`0911223344`", card)

if __name__ == "__main__":
    unittest.main()
