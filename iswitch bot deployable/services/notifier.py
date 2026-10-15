import os
import asyncio
import logging
from typing import Optional, List
from config import ADMIN_USER_IDS, CUSTOMER_BOT_TOKEN
from services.ui_utils import format_admin_order_card

logger = logging.getLogger("iswitch.notifier")

class NotifierService:
    def __init__(self):
        self.customer_bot_app = None
        self.admin_bot_app = None

    def register_bots(self, customer_bot_app, admin_bot_app):
        self.customer_bot_app = customer_bot_app
        self.admin_bot_app = admin_bot_app
        logger.info("Registered bot applications with NotifierService.")

    async def notify_admins_new_order(self, order: dict):
        """Sends notification to all whitelisted admins when an order is created without immediate receipt."""
        if not self.admin_bot_app:
            logger.warning("Admin bot app not registered; skipping admin notification.")
            return

        order_id = order["order_id"]
        text = format_admin_order_card(order, title="NEW ORDER (Pending Slip)")

        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        row1 = [InlineKeyboardButton("👁 View Order Details", callback_data=f"adm_ord_view_{order_id}")]
        tg_uid = order.get("telegram_user_id")
        if tg_uid:
            row1.append(InlineKeyboardButton("💬 Chat Customer", url=f"tg://user?id={tg_uid}"))
        else:
            row1.append(InlineKeyboardButton("📞 Call Customer", callback_data=f"adm_call_{order_id}"))

        keyboard_rows = [row1]
        lat = order.get("delivery_latitude")
        lng = order.get("delivery_longitude")
        row2 = []
        if lat is not None and lng is not None:
            row2.append(InlineKeyboardButton("🗺 Open Map", url=f"https://maps.google.com/?q={lat},{lng}"))
        row2.append(InlineKeyboardButton("❌ Cancel Order", callback_data=f"adm_ord_st_{order_id}_Cancelled"))
        keyboard_rows.append(row2)
        keyboard = InlineKeyboardMarkup(keyboard_rows)

        async def _send_to_admin(admin_id: int):
            try:
                await self.admin_bot_app.bot.send_message(
                    chat_id=admin_id,
                    text=text,
                    parse_mode="Markdown",
                    reply_markup=keyboard
                )
            except Exception as e:
                # If markdown fails, retry plain text
                try:
                    await self.admin_bot_app.bot.send_message(
                        chat_id=admin_id,
                        text=text,
                        parse_mode=None,
                        reply_markup=keyboard
                    )
                except Exception:
                    logger.warning(f"Failed to send order notification to admin {admin_id}: {e}")

        await asyncio.gather(*[_send_to_admin(aid) for aid in ADMIN_USER_IDS], return_exceptions=True)

    async def notify_admins_receipt_uploaded(
        self,
        order: dict,
        receipt_path: Optional[str] = None,
        telegram_file_id: Optional[str] = None,
        is_photo: bool = True
    ):
        """
        Sends the complete, finalized order notification with the uploaded receipt
        and full order details right when the customer completes payment.
        Guaranteed sub-second delivery to admins via Telegram cloud cache and instant text fallback.
        """
        if not self.admin_bot_app:
            return

        order_id = order["order_id"]
        order_num = order.get("order_number", "N/A")
        cust_name = order.get("delivery_name") or order.get("customer_name") or "Customer"

        caption = format_admin_order_card(order, title="NEW ORDER & RECEIPT")
        if len(caption) > 1020:
            caption = caption[:1015] + "..."

        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        rows = [
            [
                InlineKeyboardButton("✅ Approve Payment", callback_data=f"adm_pay_appr_{order_id}"),
                InlineKeyboardButton("❌ Reject Payment", callback_data=f"adm_pay_rej_{order_id}")
            ]
        ]

        row_tools = []
        tg_uid = order.get("telegram_user_id")
        if tg_uid:
            row_tools.append(InlineKeyboardButton("💬 Chat Customer", url=f"tg://user?id={tg_uid}"))
        else:
            row_tools.append(InlineKeyboardButton("📞 Customer Details", callback_data=f"adm_call_{order_id}"))

        lat = order.get("delivery_latitude")
        lng = order.get("delivery_longitude")
        if lat is not None and lng is not None:
            row_tools.append(InlineKeyboardButton("🗺 Map", url=f"https://maps.google.com/?q={lat},{lng}"))

        rows.append(row_tools)
        rows.append([InlineKeyboardButton("👁 View Full Order", callback_data=f"adm_ord_view_{order_id}")])
        keyboard = InlineKeyboardMarkup(rows)

        async def _send_admin(admin_id: int):
            sent_admin_msg = False
            # 1. Attempt sending photo with full action keyboard via Admin Bot if local file is ready
            if receipt_path and os.path.isfile(receipt_path):
                try:
                    if receipt_path.lower().endswith((".jpg", ".jpeg", ".png")):
                        with open(receipt_path, "rb") as photo_file:
                            await self.admin_bot_app.bot.send_photo(
                                chat_id=admin_id,
                                photo=photo_file,
                                caption=caption,
                                parse_mode="Markdown",
                                reply_markup=keyboard
                            )
                    else:
                        with open(receipt_path, "rb") as doc_file:
                            await self.admin_bot_app.bot.send_document(
                                chat_id=admin_id,
                                document=doc_file,
                                caption=caption,
                                parse_mode="Markdown",
                                reply_markup=keyboard
                            )
                    sent_admin_msg = True
                except Exception as e:
                    # Retry with plain caption if markdown failed
                    try:
                        if receipt_path.lower().endswith((".jpg", ".jpeg", ".png")):
                            with open(receipt_path, "rb") as photo_file:
                                await self.admin_bot_app.bot.send_photo(
                                    chat_id=admin_id,
                                    photo=photo_file,
                                    caption=caption,
                                    parse_mode=None,
                                    reply_markup=keyboard
                                )
                        else:
                            with open(receipt_path, "rb") as doc_file:
                                await self.admin_bot_app.bot.send_document(
                                    chat_id=admin_id,
                                    document=doc_file,
                                    caption=caption,
                                    parse_mode=None,
                                    reply_markup=keyboard
                                )
                        sent_admin_msg = True
                    except Exception as inner_e:
                        logger.warning(f"Failed to send local receipt file to admin {admin_id}: {inner_e}")

            # 2. If photo wasn't sent (no local file yet or transfer error), send full order text + buttons immediately
            if not sent_admin_msg:
                try:
                    await self.admin_bot_app.bot.send_message(
                        chat_id=admin_id,
                        text=caption,
                        parse_mode="Markdown",
                        reply_markup=keyboard
                    )
                except Exception:
                    try:
                        await self.admin_bot_app.bot.send_message(
                            chat_id=admin_id,
                            text=caption,
                            parse_mode=None,
                            reply_markup=keyboard
                        )
                    except Exception as text_e:
                        logger.warning(f"Failed to send order notification text to admin {admin_id}: {text_e}")

            # 3. Deliver photo to admin via Admin Bot (NOT customer bot, avoiding echoing receipt back to customer)
            if telegram_file_id and self.customer_bot_app and self.admin_bot_app and not sent_admin_msg:
                try:
                    tg_file = await self.customer_bot_app.bot.get_file(telegram_file_id)
                    if tg_file and tg_file.file_path:
                        if is_photo:
                            await self.admin_bot_app.bot.send_photo(
                                chat_id=admin_id,
                                photo=tg_file.file_path,
                                caption=f"🧾 *Uploaded Receipt Proof*\nOrder: `{order_num}` | Customer: {cust_name}",
                                parse_mode="Markdown"
                            )
                        else:
                            await self.admin_bot_app.bot.send_document(
                                chat_id=admin_id,
                                document=tg_file.file_path,
                                caption=f"🧾 *Uploaded Receipt Proof*\nOrder: `{order_num}` | Customer: {cust_name}",
                                parse_mode="Markdown"
                            )
                except Exception as c_err:
                    logger.warning(f"Cloud media relay to admin {admin_id} skipped: {c_err}")

        await asyncio.gather(*[_send_admin(aid) for aid in ADMIN_USER_IDS], return_exceptions=True)

    async def notify_customer_payment_rejected(
        self,
        telegram_user_id: int,
        order_number: str,
        reason: str,
        order_id: Optional[int] = None
    ) -> bool:
        """Sends immediate payment rejection notification to customer with reason and re-upload button."""
        if not telegram_user_id:
            logger.warning("notify_customer_payment_rejected skipped: missing telegram_user_id")
            return False

        bot_instance = self.customer_bot_app.bot if self.customer_bot_app else None
        if not bot_instance and CUSTOMER_BOT_TOKEN:
            from telegram import Bot
            bot_instance = Bot(token=CUSTOMER_BOT_TOKEN)

        if not bot_instance:
            logger.error("notify_customer_payment_rejected failed: no customer bot instance or token available")
            return False

        text = (
            f"❌ *Payment Receipt Rejected*\n\n"
            f"Your payment verification for order *#{order_number}* could not be approved.\n\n"
            f"📋 *Reason:*\n"
            f"⚠️ {reason}\n\n"
            f"Please tap *📤 Upload New Receipt* below to submit a clear, valid payment confirmation."
        )

        plain_text = (
            f"❌ Payment Receipt Rejected\n\n"
            f"Your payment verification for order #{order_number} could not be approved.\n\n"
            f"Reason:\n"
            f"⚠️ {reason}\n\n"
            f"Please tap 'Upload New Receipt' below to submit a clear, valid payment confirmation."
        )

        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        buttons = []
        if order_id:
            buttons.append([InlineKeyboardButton("📤 Upload New Receipt", callback_data=f"ord_upload_rcpt_{order_id}")])
            buttons.append([InlineKeyboardButton("📦 View Order Details", callback_data=f"ord_view_{order_id}")])
        else:
            buttons.append([InlineKeyboardButton("📦 View Order Details", callback_data=f"ord_view_{order_number}")])
        buttons.append([InlineKeyboardButton("🛍 Shop More", callback_data="cust_shop")])
        keyboard = InlineKeyboardMarkup(buttons)

        try:
            await bot_instance.send_message(
                chat_id=telegram_user_id,
                text=text,
                parse_mode="Markdown",
                reply_markup=keyboard
            )
            logger.info(f"Payment rejection notification sent to customer {telegram_user_id} for order #{order_number}")
            return True
        except Exception as e:
            logger.warning(f"Markdown send failed for customer {telegram_user_id}, retrying plain text: {e}")
            try:
                await bot_instance.send_message(
                    chat_id=telegram_user_id,
                    text=plain_text,
                    parse_mode=None,
                    reply_markup=keyboard
                )
                logger.info(f"Payment rejection notification sent (plain text) to customer {telegram_user_id} for order #{order_number}")
                return True
            except Exception as e2:
                logger.error(f"Failed to notify customer {telegram_user_id} about payment rejection: {e2}")
                return False

    async def notify_customer_order_status(
        self,
        telegram_user_id: int,
        order_number: str,
        new_status: str,
        extra_msg: str = "",
        order_id: Optional[int] = None
    ) -> bool:
        """Sends status update notification to the customer."""
        if not telegram_user_id:
            logger.warning("notify_customer_order_status skipped: missing telegram_user_id")
            return False

        bot_instance = self.customer_bot_app.bot if self.customer_bot_app else None
        if not bot_instance and CUSTOMER_BOT_TOKEN:
            from telegram import Bot
            bot_instance = Bot(token=CUSTOMER_BOT_TOKEN)

        if not bot_instance:
            logger.error("notify_customer_order_status failed: no customer bot instance or token available")
            return False

        status_emojis = {
            "Pending": "🟡",
            "Payment Pending": "💳",
            "Payment Confirmed": "✅",
            "Payment Rejected": "❌",
            "Preparing": "📦",
            "Out for Delivery": "🚚",
            "Delivered": "🎉",
            "Cancelled": "❌",
            "Refunded": "↩️"
        }
        emoji = status_emojis.get(new_status, "ℹ️")

        text = (
            f"{emoji} *Order Status Update*\n\n"
            f"Your order *#{order_number}* is now:\n"
            f"👉 *{new_status}*\n\n"
        )
        if extra_msg:
            text += f"{extra_msg}\n\n"

        text += "Thank you for shopping with iSwitch!"

        plain_text = (
            f"{emoji} Order Status Update\n\n"
            f"Your order #{order_number} is now:\n"
            f"👉 {new_status}\n\n"
        )
        if extra_msg:
            plain_text += f"{extra_msg}\n\n"

        plain_text += "Thank you for shopping with iSwitch!"

        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        buttons = []
        if order_id:
            if new_status in ["Payment Pending", "Payment Rejected"]:
                buttons.append([InlineKeyboardButton("📤 Upload Receipt", callback_data=f"ord_upload_rcpt_{order_id}")])
            buttons.append([InlineKeyboardButton("📦 View Order Details", callback_data=f"ord_view_{order_id}")])
        else:
            buttons.append([InlineKeyboardButton("📦 View Order Details", callback_data=f"ord_view_{order_number}")])
        buttons.append([InlineKeyboardButton("🛍 Shop More", callback_data="cust_shop")])
        keyboard = InlineKeyboardMarkup(buttons)

        try:
            await bot_instance.send_message(
                chat_id=telegram_user_id,
                text=text,
                parse_mode="Markdown",
                reply_markup=keyboard
            )
            logger.info(f"Order status notification sent to customer {telegram_user_id} for order #{order_number} (status: {new_status})")
            return True
        except Exception as e:
            try:
                await bot_instance.send_message(
                    chat_id=telegram_user_id,
                    text=plain_text,
                    parse_mode=None,
                    reply_markup=keyboard
                )
                logger.info(f"Order status notification sent (plain text) to customer {telegram_user_id} for order #{order_number}")
                return True
            except Exception as e2:
                logger.warning(f"Failed to notify customer {telegram_user_id}: {e2}")
                return False

    async def broadcast_announcement(self, user_ids: List[int], text: str) -> int:
        """Sends broadcast announcement to customers."""
        if not self.customer_bot_app:
            return 0

        sent_count = 0
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🛍 Start Shopping", callback_data="cust_shop")]
        ])

        for uid in user_ids:
            try:
                await self.customer_bot_app.bot.send_message(
                    chat_id=uid,
                    text=text,
                    parse_mode="Markdown",
                    reply_markup=kb
                )
                sent_count += 1
            except Exception:
                try:
                    await self.customer_bot_app.bot.send_message(
                        chat_id=uid,
                        text=text,
                        parse_mode=None,
                        reply_markup=kb
                    )
                    sent_count += 1
                except Exception:
                    pass

        return sent_count

notifier = NotifierService()
