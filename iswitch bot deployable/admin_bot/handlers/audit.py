import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from admin_bot.handlers.auth import verify_admin_access
from database.crud import get_recent_audit_logs
from services.ui_utils import safe_edit_or_send

logger = logging.getLogger("iswitch.admin.audit")

async def audit_logs_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verify_admin_access(update, context):
        return

    logs = await get_recent_audit_logs(limit=15)
    text = "📋 *Recent Administrative Audit Logs*\n\n"

    if not logs:
        text += "_No audit logs recorded yet._"
    else:
        for l in logs:
            action = l.get("action", "").replace("_", " ").title()
            target = f"{l.get('target_type')} #{l.get('target_id')}"
            admin_str = f"Admin {l.get('admin_id')}"
            ts = l.get("timestamp", "")[:16]
            prev_val = f" (Old: {l['previous_value']})" if l.get("previous_value") else ""
            new_val = f" -> (New: {l['new_value']})" if l.get("new_value") else ""
            text += f"• `{ts}`: *{admin_str}* performed *{action}* on `{target}`{prev_val}{new_val}\n"

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Refresh Logs", callback_data="adm_audit_logs")],
        [InlineKeyboardButton("🏠 Admin Menu", callback_data="adm_main")]
    ])

    await safe_edit_or_send(update, context, text, reply_markup=kb)
