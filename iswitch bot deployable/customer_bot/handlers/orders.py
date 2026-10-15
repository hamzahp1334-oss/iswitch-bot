import logging
from telegram import Update
from telegram.ext import ContextTypes
from database.crud import (
    get_customer_by_telegram_id, list_orders_for_customer, get_order_by_id, get_order_by_number
)
from customer_bot.keyboards import orders_list_keyboard, order_detail_keyboard
from services.ui_utils import safe_edit_or_send, escape_md

logger = logging.getLogger("iswitch.cust.orders")

async def my_orders_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    cust = await get_customer_by_telegram_id(user.id)
    if not cust:
        msg = "📦 *My Orders*\n\nNo orders yet. Tap Shop to start!"
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🛍 Shop Now", callback_data="cust_shop")]])
        await safe_edit_or_send(update, context, text=msg, reply_markup=kb)
        return

    orders = await list_orders_for_customer(cust["customer_id"], limit=10)
    if not orders:
        msg = "📦 *My Orders*\n\nNo orders yet. Tap Shop to start!"
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🛍 Shop Now", callback_data="cust_shop")]])
        await safe_edit_or_send(update, context, text=msg, reply_markup=kb)
        return

    msg = f"📦 *My Orders ({len(orders)})*\n\nTap an order to view status or upload receipt:"
    kb = orders_list_keyboard(orders)
    await safe_edit_or_send(update, context, text=msg, reply_markup=kb)

async def order_detail_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    param = query.data.replace("ord_view_", "").strip()
    if param.isdigit():
        order_id = int(param)
        order = await get_order_by_id(order_id)
    else:
        order = await get_order_by_number(param)
        order_id = order["order_id"] if order else None

    if not order:
        await query.answer("Order not found.", show_alert=True)
        return

    # Security: Verify that the caller actually owns this order (IDOR protection)
    user = update.effective_user
    cust = await get_customer_by_telegram_id(user.id)
    if not cust or order.get("customer_id") != cust["customer_id"]:
        await query.answer("⛔ Access denied: You do not own this order.", show_alert=True)
        return

    num = order["order_number"]
    date_str = order.get("created_at", "")[:16]
    ord_status = order.get("order_status", "Pending")
    pay_status = order.get("payment_status", "Pending")
    total = order.get("total", 0.0)
    currency = order.get("currency", "ETB")

    status_emojis = {
        "Pending": "🟡",
        "Payment Pending": "💳",
        "Payment Confirmed": "✅",
        "Preparing": "📦",
        "Out for Delivery": "🚚",
        "Delivered": "🎉",
        "Cancelled": "❌"
    }
    st_emoji = status_emojis.get(ord_status, "📋")

    lines = [
        f"📦 *Order #{num}*\n",
        f"📊 *Status:* {st_emoji} *{ord_status}*",
        f"💳 *Payment:* *{pay_status}*",
        f"📅 *Date:* `{date_str}`\n",
        "🛒 *Items:*"
    ]

    for it in order.get("items", []):
        pname = escape_md(it.get("product_name") or "Product")
        lines.append(f"• {pname} ({it['quantity']}x) — {it['total_price']:,.0f} {currency}")

    lines.append(f"\nSubtotal: {order['subtotal']:,.0f} {currency}")
    lines.append(f"Delivery: {order['delivery_fee']:,.0f} {currency}")
    lines.append(f"💰 *Total: {total:,.0f} {currency}*\n")

    lines.append("📍 *Delivery:*")
    lines.append(f"👤 {escape_md(order.get('delivery_name', ''))} (`{order.get('delivery_phone', '')}`)")
    lines.append(f"🏙 {escape_md(order.get('delivery_city', ''))}, {escape_md(order.get('delivery_area', ''))}")
    if order.get("delivery_address"):
        lines.append(f"🏠 {escape_md(order['delivery_address'])}")

    delivery = order.get("delivery")
    if delivery and delivery.get("status") == "Out for Delivery":
        driver_name = escape_md(delivery.get("delivery_person", "iSwitch Driver"))
        lines.append(f"\n🚚 *Courier:* {driver_name}")
        if delivery.get("delivery_phone"):
            lines.append(f"📞 Courier Phone: `{delivery.get('delivery_phone')}`")

    payment = order.get("payment")
    if payment and payment.get("rejection_reason"):
        lines.append(f"\n⚠️ *Note:* {escape_md(payment['rejection_reason'])}")

    text = "\n".join(lines)
    kb = order_detail_keyboard(order)
    await safe_edit_or_send(update, context, text=text, reply_markup=kb)

async def prompt_reupload_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    order_id = int(query.data.replace("ord_upload_rcpt_", ""))
    order = await get_order_by_id(order_id)
    if not order:
        await query.answer("Order not found.", show_alert=True)
        return

    # Security: Verify that the caller actually owns this order (IDOR protection)
    user = update.effective_user
    cust = await get_customer_by_telegram_id(user.id)
    if not cust or order.get("customer_id") != cust["customer_id"]:
        await query.answer("⛔ Access denied: You do not own this order.", show_alert=True)
        return

    context.user_data["current_order_id"] = order_id
    context.user_data["awaiting_standalone_receipt"] = True

    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    cancel_kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅ Back to Order", callback_data=f"ord_view_{order_id}")]])

    msg = (
        "📸 *Upload Receipt*\n\n"
        "Please send your payment screenshot or slip:"
    )
    await safe_edit_or_send(update, context, text=msg, reply_markup=cancel_kb)
