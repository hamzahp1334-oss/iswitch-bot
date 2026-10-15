import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from admin_bot.handlers.auth import verify_admin_access
from database.db import db
from services.notifier import notifier
from services.audit import log_admin_action
from services.ui_utils import safe_edit_or_send

logger = logging.getLogger("iswitch.admin.announcements")

async def announcements_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verify_admin_access(update, context):
        return

    text = (
        "📢 *Customer Broadcast & Announcements*\n\n"
        "Send promotional updates, new arrival alerts, or notifications to customers.\n"
        "To prevent accidental sending, messages must be previewed and confirmed before broadcast.\n\n"
        "Select an announcement type below to compose:"
    )

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔥 New Arrival Alert", callback_data="adm_bc_compose_new_arrival")],
        [InlineKeyboardButton("🏷 Special Discount / Sale", callback_data="adm_bc_compose_discount")],
        [InlineKeyboardButton("📢 General Announcement", callback_data="adm_bc_compose_general")],
        [InlineKeyboardButton("🏠 Admin Menu", callback_data="adm_main")]
    ])

    await safe_edit_or_send(update, context, text, reply_markup=kb)

async def compose_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verify_admin_access(update, context):
        return

    query = update.callback_query
    # Set broadcast type in session
    b_type = query.data.replace("adm_bc_compose_", "")
    context.user_data["broadcast_type"] = b_type
    context.user_data["awaiting_broadcast_text"] = True

    kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅ Cancel", callback_data="adm_broadcast")]])
    msg = f"📝 *Compose {b_type.replace('_', ' ').title()}*\n\nPlease reply with the message text you wish to broadcast to customers:"
    await safe_edit_or_send(update, context, msg, reply_markup=kb)

async def handle_broadcast_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if not context.user_data.get("awaiting_broadcast_text"):
        return False

    context.user_data["awaiting_broadcast_text"] = False
    text = update.message.text.strip()
    context.user_data["pending_broadcast_text"] = text

    # Count customers
    rows = await db.fetch_all("SELECT telegram_user_id FROM customers WHERE telegram_user_id IS NOT NULL;")
    recipient_count = len(rows)

    preview_msg = (
        f"⚠️ *BROADCAST CONFIRMATION*\n\n"
        f"Target: *All Registered Customers ({recipient_count} users)*\n\n"
        f"━━━━━━━━ MESSAGE PREVIEW ━━━━━━━━\n"
        f"{text}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Are you sure you want to send this broadcast?"
    )

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 Confirm & Send to All", callback_data="adm_bc_send_execute")],
        [InlineKeyboardButton("❌ Discard", callback_data="adm_broadcast")]
    ])

    await update.message.reply_text(preview_msg, parse_mode="Markdown", reply_markup=kb)
    return True

async def execute_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verify_admin_access(update, context):
        return

    query = update.callback_query
    # Security: Atomically consume draft text to prevent double-click / replay attacks
    text = context.user_data.pop("pending_broadcast_text", None)
    if not text:
        await query.answer("Broadcast already sent or no draft found.", show_alert=True)
        return

    rows = await db.fetch_all("SELECT telegram_user_id FROM customers WHERE telegram_user_id IS NOT NULL;")
    uids = [r["telegram_user_id"] for r in rows]

    await safe_edit_or_send(update, context, "⏳ Sending broadcast to customers in background...")
    sent = await notifier.broadcast_announcement(uids, text)
    await log_admin_action(update.effective_user.id, "broadcast_sent", "announcement", "all", details=f"Sent to {sent} users")

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Broadcasts", callback_data="adm_broadcast")],
        [InlineKeyboardButton("🏠 Admin Menu", callback_data="adm_main")]
    ])
    await safe_edit_or_send(update, context, f"✅ Broadcast successfully sent to *{sent}* customers!", reply_markup=kb)
