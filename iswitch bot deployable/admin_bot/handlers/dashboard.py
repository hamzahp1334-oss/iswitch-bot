import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from admin_bot.handlers.auth import verify_admin_access
from admin_bot.keyboards import admin_main_menu_keyboard
from database.crud import get_dashboard_metrics, get_setting
from services.ui_utils import safe_edit_or_send

logger = logging.getLogger("iswitch.admin.dashboard")

async def admin_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verify_admin_access(update, context):
        return

    user = update.effective_user
    store_name = await get_setting("store_name", "iSwitch Store")

    text = (
        f"🔐 *iSwitch Administrative Control System*\n\n"
        f"Welcome, *{user.first_name}* (ID: `{user.id}`)\n"
        f"Store: *{store_name}*\n\n"
        f"Select an administrative module below to manage the store:"
    )

    await safe_edit_or_send(update, context, text, reply_markup=admin_main_menu_keyboard())

async def dashboard_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verify_admin_access(update, context):
        return

    m = await get_dashboard_metrics()
    currency = await get_setting("currency", "ETB")

    text = (
        "📊 *iSwitch Real-Time Executive Dashboard*\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "📦 *PRODUCT INVENTORY*\n"
        f"• Total Products: *{m['total_products']}*\n"
        f"• Available: 🟢 *{m['available_products']}*\n"
        f"• Sold: 🔴 *{m['sold_products']}*\n"
        f"• Out of Stock: 🟡 *{m['out_of_stock']}*\n\n"
        "🛒 *ORDER METRICS*\n"
        f"• Total Orders: *{m['total_orders']}*\n"
        f"• Pending/Processing: 🟡 *{m['pending_orders']}*\n"
        f"• Delivered/Completed: ✅ *{m['completed_orders']}*\n\n"
        "💳 *FINANCIALS & PAYMENTS*\n"
        f"• Verified Payments: ✅ *{m['verified_payments']}*\n"
        f"• Awaiting Verification: ⏳ *{m['pending_payments']}*\n"
        f"• Total Realized Revenue: 💰 *{m['total_sales']:,.2f} {currency}*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "📂 *INVENTORY BY CATEGORY*\n"
    )

    if m.get("category_distribution"):
        for cat in m["category_distribution"]:
            text += f"• {cat['name']}: *{cat['count']}*\n"
    else:
        text += "_No category data available._\n"

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Refresh Stats", callback_data="adm_dash"), InlineKeyboardButton("📦 Products", callback_data="adm_prods")],
        [InlineKeyboardButton("🛒 View Orders", callback_data="adm_ords"), InlineKeyboardButton("💳 Verify Payments", callback_data="adm_payments")],
        [InlineKeyboardButton("🏠 Admin Menu", callback_data="adm_main")]
    ])

    await safe_edit_or_send(update, context, text, reply_markup=kb)

async def reports_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verify_admin_access(update, context):
        return

    m = await get_dashboard_metrics()
    currency = await get_setting("currency", "ETB")

    text = (
        "📈 *Store Performance & Sales Report*\n\n"
        f"💰 *Gross Verified Sales:* `{m['total_sales']:,.2f} {currency}`\n"
        f"🛒 *Total Transactions:* `{m['total_orders']}`\n\n"
        "📊 *Order Status Breakdown:*\n"
    )

    if m.get("order_status_distribution"):
        for st in m["order_status_distribution"]:
            text += f"• {st['order_status']}: *{st['count']} orders*\n"
    else:
        text += "_No order status records yet._\n"

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Dashboard", callback_data="adm_dash"), InlineKeyboardButton("🏠 Admin Menu", callback_data="adm_main")]
    ])

    await safe_edit_or_send(update, context, text, reply_markup=kb)
