import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from admin_bot.handlers.auth import verify_admin_access
from database.crud import search_customers, get_customer_by_id, get_customer_stats
from services.ui_utils import safe_edit_or_send

logger = logging.getLogger("iswitch.admin.customers")

async def customers_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verify_admin_access(update, context):
        return

    custs = await search_customers("", limit=10)
    text = f"👥 *Customer Management* ({len(custs)} recent customers):\n\nSelect a customer to view order history and delivery address:"

    buttons = []
    for c in custs:
        name = c.get("full_name") or c.get("telegram_username") or f"User #{c['telegram_user_id']}"
        phone = c.get("phone") or "No phone"
        buttons.append([InlineKeyboardButton(f"👤 {name} ({phone})", callback_data=f"adm_cview_{c['customer_id']}")])

    buttons.append([
        InlineKeyboardButton("🔎 Search Customer", callback_data="adm_csearch"),
        InlineKeyboardButton("🏠 Admin Menu", callback_data="adm_main")
    ])

    kb = InlineKeyboardMarkup(buttons)
    await safe_edit_or_send(update, context, text, reply_markup=kb)

async def prompt_customer_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verify_admin_access(update, context):
        return

    context.user_data["awaiting_admin_cust_search"] = True
    msg = (
        "🔎 *Search Customers*\n\n"
        "Please reply with a customer name, phone number, or username:\n"
        "_(e.g., Abebe, 0980632130, israel)_"
    )
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅ Cancel", callback_data="adm_custs")]])
    await safe_edit_or_send(update, context, msg, reply_markup=kb)

async def handle_customer_search_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if not context.user_data.get("awaiting_admin_cust_search"):
        return False

    context.user_data["awaiting_admin_cust_search"] = False
    term = update.message.text.strip()
    custs = await search_customers(term, limit=15)

    if not custs:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔎 Search Again", callback_data="adm_csearch")],
            [InlineKeyboardButton("👥 All Customers", callback_data="adm_custs")]
        ])
        await update.message.reply_text(f"🔎 No customers found matching '*{term}*'.", parse_mode="Markdown", reply_markup=kb)
        return True

    text = f"🔎 *Search Results for:* '_{term}_' ({len(custs)} customers found):\n\nSelect a customer to view profile:"
    buttons = []
    for c in custs:
        name = c.get("full_name") or c.get("telegram_username") or f"User #{c['telegram_user_id']}"
        phone = c.get("phone") or "No phone"
        buttons.append([InlineKeyboardButton(f"👤 {name} ({phone})", callback_data=f"adm_cview_{c['customer_id']}")])
    buttons.append([InlineKeyboardButton("⬅ Customers Menu", callback_data="adm_custs")])

    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
    return True

async def customer_view_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verify_admin_access(update, context):
        return

    query = update.callback_query
    cid = int(query.data.replace("adm_cview_", ""))
    c = await get_customer_by_id(cid)
    if not c:
        await query.answer("Customer not found.", show_alert=True)
        return

    stats = await get_customer_stats(cid)

    name = c.get("full_name") or "N/A"
    tg_u = f"@{c['telegram_username']}" if c.get("telegram_username") else "No username"
    phone = c.get("phone") or "N/A"
    city = c.get("city") or "N/A"
    area = c.get("area") or "N/A"
    address = c.get("address") or "N/A"
    created = c.get("created_at", "")[:10]

    lines = [
        f"👤 *CUSTOMER PROFILE: #{cid}*\n",
        f"• *Name:* {name}",
        f"• *Telegram:* {tg_u} (ID: `{c['telegram_user_id']}`)",
        f"• *Phone:* `{phone}`",
        f"• *Location:* {city}, {area}",
        f"• *Address:* {address}",
        f"• *Registered:* {created}\n",
        "📊 *Shopping Activity:*",
        f"• Total Orders: *{stats['order_count']}*",
        f"• Lifetime Spend: *{stats['total_spent']:,.2f} ETB*"
    ]

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 Send Message via Telegram", url=f"tg://user?id={c['telegram_user_id']}")],
        [InlineKeyboardButton("⬅ Back to Customers", callback_data="adm_custs"), InlineKeyboardButton("🏠 Admin Menu", callback_data="adm_main")]
    ])

    await safe_edit_or_send(update, context, "\n".join(lines), reply_markup=kb)
