import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from admin_bot.handlers.auth import verify_admin_access
from admin_bot.keyboards import admin_orders_keyboard, admin_order_detail_keyboard
from database.crud import (
    list_orders_admin, get_order_by_id, get_customer_by_id, update_order_status,
    verify_payment, update_admin_notes, get_receipts_for_order
)
from services.audit import log_admin_action
from services.notifier import notifier
from services.ui_utils import safe_edit_or_send, safe_edit_caption_or_send, format_admin_order_card

logger = logging.getLogger("iswitch.admin.orders")

PAGE_SIZE = 6

async def orders_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verify_admin_access(update, context):
        return

    orders, total = await list_orders_admin(status="All", limit=PAGE_SIZE, offset=0)
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)

    text = f"🛒 *Order Management* (Total: {total} orders)\n\nFilter by status or tap an order to view customer details, receipt, and fulfillment:"
    kb = admin_orders_keyboard(orders, current_filter="All", page=1, total_pages=total_pages)
    await safe_edit_or_send(update, context, text, reply_markup=kb)

async def payments_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Direct route for '💳 Payments' from main dashboard."""
    if not await verify_admin_access(update, context):
        return

    orders, total = await list_orders_admin(status="Payment Pending", limit=PAGE_SIZE, offset=0)
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)

    text = f"💳 *Payment Verification Queue* (Pending: {total})\n\nSelect an order to verify receipt and confirm payment:"
    kb = admin_orders_keyboard(orders, current_filter="Payment Pending", page=1, total_pages=total_pages)
    await safe_edit_or_send(update, context, text, reply_markup=kb)

async def orders_filter_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verify_admin_access(update, context):
        return

    query = update.callback_query
    status_filter = query.data.replace("adm_ord_flt_", "")
    orders, total = await list_orders_admin(status=status_filter, limit=PAGE_SIZE, offset=0)
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)

    text = f"🛒 *Orders Filtered by: {status_filter}* (Found {total})\n\nSelect an order to view:"
    kb = admin_orders_keyboard(orders, current_filter=status_filter, page=1, total_pages=total_pages)
    await safe_edit_or_send(update, context, text, reply_markup=kb)

async def orders_pagination_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verify_admin_access(update, context):
        return

    query = update.callback_query
    # adm_ord_pg_{filter}_{page}
    remainder = query.data.replace("adm_ord_pg_", "")
    parts = remainder.rsplit("_", 1)
    status_filter = parts[0]
    page = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 1

    offset = (page - 1) * PAGE_SIZE
    orders, total = await list_orders_admin(status=status_filter, limit=PAGE_SIZE, offset=offset)
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)

    text = f"🛒 *Orders Filtered by: {status_filter}* (Page {page}/{total_pages} - Total {total}):\n\nSelect an order to view:"
    kb = admin_orders_keyboard(orders, current_filter=status_filter, page=page, total_pages=total_pages)
    await safe_edit_or_send(update, context, text, reply_markup=kb)

async def prompt_order_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verify_admin_access(update, context):
        return

    context.user_data["awaiting_admin_order_search"] = True
    msg = (
        "🔎 *Search Orders*\n\n"
        "Please reply with an Order Number, Customer Name, or Phone Number:\n"
        "_(e.g., ISW-260928, 0980632130, Abebe)_"
    )
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅ Cancel", callback_data="adm_ords")]])
    await safe_edit_or_send(update, context, msg, reply_markup=kb)

async def handle_order_search_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if not context.user_data.get("awaiting_admin_order_search"):
        return False

    context.user_data["awaiting_admin_order_search"] = False
    term = update.message.text.strip()

    orders, total = await list_orders_admin(status="All", limit=20, offset=0, search=term)
    if not orders:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔎 Search Again", callback_data="adm_ord_search")],
            [InlineKeyboardButton("🛒 All Orders", callback_data="adm_ords")]
        ])
        await update.message.reply_text(f"🔎 No orders found matching '*{term}*'.", parse_mode="Markdown", reply_markup=kb)
        return True

    text = f"🔎 *Search Results for:* '_{term}_' ({len(orders)} orders found):\n\nTap an order to inspect:"
    kb = admin_orders_keyboard(orders, current_filter="All", page=1, total_pages=1)
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)
    return True

async def order_view_admin(update: Update, context: ContextTypes.DEFAULT_TYPE, oid: int = None):
    if not await verify_admin_access(update, context):
        return

    query = update.callback_query
    if oid is None:
        if query and query.data:
            oid = int(query.data.replace("adm_ord_view_", ""))
        else:
            return

    order = await get_order_by_id(oid)
    if not order:
        if query:
            await query.answer("Order not found.", show_alert=True)
        return

    receipts = await get_receipts_for_order(oid)
    order["receipts"] = receipts

    text = format_admin_order_card(order, title="ORDER")
    kb = admin_order_detail_keyboard(order)

    # Use safe caption editing if this is on a receipt photo message
    await safe_edit_caption_or_send(update, context, text, reply_markup=kb)

async def view_receipt_photo_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verify_admin_access(update, context):
        return

    query = update.callback_query
    await query.answer()
    oid = int(query.data.replace("adm_rcpt_view_", ""))
    receipts = await get_receipts_for_order(oid)
    if not receipts:
        await query.answer("No receipt uploaded for this order yet.", show_alert=True)
        return

    latest_rcpt = receipts[0]
    file_path = latest_rcpt.get("file_path")
    if file_path and os.path.isfile(file_path):
        try:
            with open(file_path, "rb") as f:
                if file_path.lower().endswith((".jpg", ".jpeg", ".png")):
                    await context.bot.send_photo(
                        chat_id=update.effective_chat.id,
                        photo=f,
                        caption=f"🧾 Receipt Photo for Order #{oid}"
                    )
                else:
                    await context.bot.send_document(
                        chat_id=update.effective_chat.id,
                        document=f,
                        caption=f"🧾 Receipt Document for Order #{oid}"
                    )
            return
        except Exception as e:
            logger.warning(f"Failed to send local receipt file: {e}")

    # Fallback to Admin Bot sending cloud file if available
    tg_file_id = latest_rcpt.get("telegram_file_id")
    if tg_file_id and notifier.customer_bot_app:
        try:
            tg_file = await notifier.customer_bot_app.bot.get_file(tg_file_id)
            if tg_file and tg_file.file_path:
                if latest_rcpt.get("file_type", "").startswith("image"):
                    await context.bot.send_photo(
                        chat_id=update.effective_chat.id,
                        photo=tg_file.file_path,
                        caption=f"🧾 Receipt for Order #{oid}"
                    )
                else:
                    await context.bot.send_document(
                        chat_id=update.effective_chat.id,
                        document=tg_file.file_path,
                        caption=f"🧾 Receipt for Order #{oid}"
                    )
                return
        except Exception as e:
            logger.warning(f"Failed to send cloud receipt file via admin bot: {e}")

    await query.answer("Receipt file is currently synchronizing or unavailable.", show_alert=True)

async def approve_payment_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verify_admin_access(update, context):
        return

    query = update.callback_query
    admin_id = update.effective_user.id
    oid = int(query.data.replace("adm_pay_appr_", ""))

    order = await get_order_by_id(oid)
    if not order:
        await query.answer("Order not found.", show_alert=True)
        return

    # Security & Idempotency: Prevent duplicate payment verification
    if order.get("payment_status") == "Verified":
        await query.answer("Payment for this order has already been verified.", show_alert=True)
        return await order_view_admin(update, context, oid=oid)

    await verify_payment(oid, admin_id=admin_id, approved=True)
    await log_admin_action(admin_id, "payment_approved", "order", oid, order.get("payment_status"), "Verified")

    # Notify Customer via Customer Bot
    tg_user_id = order.get("telegram_user_id")
    if not tg_user_id and order.get("customer_id"):
        cust = await get_customer_by_id(order["customer_id"])
        if cust:
            tg_user_id = cust.get("telegram_user_id")

    if tg_user_id:
        await notifier.notify_customer_order_status(
            telegram_user_id=tg_user_id,
            order_number=order["order_number"],
            new_status="Payment Confirmed",
            extra_msg="We have verified your payment receipt. Your order is now being prepared for delivery!",
            order_id=oid
        )

    await query.answer("✅ Payment Verified & Order Confirmed!")
    await order_view_admin(update, context, oid=oid)

async def reject_payment_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verify_admin_access(update, context):
        return

    query = update.callback_query
    oid = int(query.data.replace("adm_pay_rej_", ""))
    context.user_data["rejecting_order_id"] = oid

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("Unclear / Blurry Image", callback_data=f"adm_pay_quickrej_{oid}_unclear")],
        [InlineKeyboardButton("Amount Does Not Match", callback_data=f"adm_pay_quickrej_{oid}_amount")],
        [InlineKeyboardButton("Duplicate / Invalid Reference", callback_data=f"adm_pay_quickrej_{oid}_duplicate")],
        [InlineKeyboardButton("⬅ Cancel", callback_data=f"adm_ord_view_{oid}")]
    ])

    prompt_text = f"❌ *Reject Payment for Order #{oid}*\n\nSelect a reason below or reply with a custom reason:"
    await safe_edit_caption_or_send(update, context, prompt_text, reply_markup=kb)

async def reject_payment_execute(update: Update, context: ContextTypes.DEFAULT_TYPE, oid: int, reason: str) -> bool:
    admin_id = update.effective_user.id
    order = await get_order_by_id(oid)
    if not order:
        logger.warning(f"reject_payment_execute: Order #{oid} not found in database!")
        return False

    await verify_payment(oid, admin_id=admin_id, approved=False, reason=reason)
    await log_admin_action(admin_id, "payment_rejected", "order", oid, order.get("payment_status"), "Rejected", details=reason)

    # Determine Customer Telegram ID
    tg_user_id = order.get("telegram_user_id")
    if not tg_user_id and order.get("customer_id"):
        cust = await get_customer_by_id(order["customer_id"])
        if cust:
            tg_user_id = cust.get("telegram_user_id")

    # Notify Customer via Customer Bot
    if tg_user_id:
        notified = await notifier.notify_customer_payment_rejected(
            telegram_user_id=tg_user_id,
            order_number=order["order_number"],
            reason=reason,
            order_id=oid
        )
        if notified:
            logger.info(f"Customer {tg_user_id} notified of payment rejection for order #{oid}")
        else:
            logger.warning(f"Failed to dispatch payment rejection notification to {tg_user_id}")
    else:
        logger.warning(f"Could not notify customer for order #{oid}: no telegram_user_id found.")

    return True

async def quick_reject_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verify_admin_access(update, context):
        return

    query = update.callback_query
    # adm_pay_quickrej_{oid}_{reason_code}
    parts = query.data.split("_")
    oid = int(parts[3])
    code = parts[4]

    reasons = {
        "unclear": "The receipt photo is unreadable or blurry. Please upload a clear photo or PDF.",
        "amount": "The transferred amount does not match the order total.",
        "duplicate": "This transaction reference was already used or cannot be found."
    }
    reason_text = reasons.get(code, "Transaction verification failed.")

    success = await reject_payment_execute(update, context, oid, reason_text)
    if success:
        await query.answer("Payment marked Rejected & Customer Notified.")
        await order_view_admin(update, context, oid=oid)
    else:
        await query.answer("⚠️ Order not found or could not be updated.", show_alert=True)

async def update_order_status_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verify_admin_access(update, context):
        return

    query = update.callback_query
    # adm_ord_st_{oid}_{status}
    remainder = query.data.replace("adm_ord_st_", "")
    oid_str, new_status = remainder.split("_", 1)
    oid = int(oid_str)

    order = await get_order_by_id(oid)
    if not order:
        await query.answer("Order not found.", show_alert=True)
        return

    old_status = order.get("order_status")
    await update_order_status(oid, new_status)
    await log_admin_action(update.effective_user.id, "order_status_change", "order", oid, old_status, new_status)

    tg_user_id = order.get("telegram_user_id")
    if not tg_user_id and order.get("customer_id"):
        cust = await get_customer_by_id(order["customer_id"])
        if cust:
            tg_user_id = cust.get("telegram_user_id")

    if tg_user_id:
        await notifier.notify_customer_order_status(
            telegram_user_id=tg_user_id,
            order_number=order["order_number"],
            new_status=new_status,
            order_id=oid
        )

    await query.answer(f"Status updated to {new_status}!")
    await order_view_admin(update, context, oid=oid)

async def handle_rejection_reason_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    oid = context.user_data.get("rejecting_order_id")
    if not oid:
        return False

    del context.user_data["rejecting_order_id"]
    reason_text = update.message.text.strip()
    success = await reject_payment_execute(update, context, oid, reason_text)
    if success:
        await update.message.reply_text(
            f"❌ Payment for Order #{oid} has been rejected and customer notified.\nReason: {reason_text}"
        )
    else:
        await update.message.reply_text(f"⚠️ Order #{oid} not found or could not be updated.")

    order = await get_order_by_id(oid)
    if order:
        kb = admin_order_detail_keyboard(order)
        await update.message.reply_text(
            f"Updated Order #{order['order_number']}:",
            reply_markup=kb
        )
    return True

async def prompt_order_notes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verify_admin_access(update, context):
        return
    query = update.callback_query
    oid = int(query.data.replace("adm_ord_notes_", ""))
    context.user_data["editing_notes_order_id"] = oid

    msg = f"📝 *Edit Admin Notes for Order #{oid}*\n\nPlease reply with your notes for this order (e.g. delivery instructions, customer special request):"
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅ Cancel", callback_data=f"adm_ord_view_{oid}")]])
    await safe_edit_or_send(update, context, msg, reply_markup=kb)

async def handle_order_notes_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    oid = context.user_data.get("editing_notes_order_id")
    if not oid:
        return False
    del context.user_data["editing_notes_order_id"]
    notes = update.message.text.strip()
    await update_admin_notes(oid, notes)
    await update.message.reply_text(f"✅ Admin notes updated for Order #{oid}!")
    order = await get_order_by_id(oid)
    if order:
        kb = admin_order_detail_keyboard(order)
        await update.message.reply_text(f"Order #{order['order_number']}:", reply_markup=kb)
    return True

async def customer_call_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verify_admin_access(update, context):
        return
    query = update.callback_query
    oid = int(query.data.replace("adm_call_", ""))
    order = await get_order_by_id(oid)
    if not order:
        await query.answer("Order not found.", show_alert=True)
        return
    phone = order.get("customer_phone") or order.get("delivery_phone") or "N/A"
    cust_name = order.get("customer_name") or order.get("delivery_name") or "Customer"
    await query.answer(f"📞 {cust_name}: {phone}", show_alert=True)
