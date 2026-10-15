import json
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from admin_bot.handlers.auth import verify_admin_access
from admin_bot.keyboards import admin_settings_keyboard
from database.crud import get_all_settings, set_setting, get_payment_methods
from services.audit import log_admin_action
from services.ui_utils import safe_edit_or_send

logger = logging.getLogger("iswitch.admin.settings")

async def settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verify_admin_access(update, context):
        return

    settings = await get_all_settings()

    text = (
        "⚙️ *System Configuration & Store Settings*\n\n"
        f"🏪 *Store Name:* {settings.get('store_name', 'iSwitch Store')}\n"
        f"📝 *Description:* {settings.get('store_description', '')}\n"
        f"💰 *Currency:* {settings.get('currency', 'ETB')}\n"
        f"🚚 *Delivery Fee:* {settings.get('delivery_fee', '150')} ETB\n"
        f"📞 *Contact Phone:* `{settings.get('contact_phone', '0980632130')}`\n"
        f"💬 *Support Username:* @{settings.get('support_username', 'israell0')}\n"
        f"📢 *Channel:* {settings.get('channel_username', '@iSwitch0')}\n\n"
        "Tap a setting below to modify:"
    )

    kb = admin_settings_keyboard()
    await safe_edit_or_send(update, context, text, reply_markup=kb)

async def prompt_delivery_fee(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verify_admin_access(update, context):
        return

    context.user_data["awaiting_setting_key"] = "delivery_fee"
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅ Cancel", callback_data="adm_settings")]])
    msg = "🚚 *Update Standard Delivery Fee*\n\nPlease enter the new delivery fee in ETB (e.g., `200`):"
    await safe_edit_or_send(update, context, msg, reply_markup=kb)

async def prompt_store_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verify_admin_access(update, context):
        return

    context.user_data["awaiting_setting_key"] = "store_name"
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅ Cancel", callback_data="adm_settings")]])
    msg = "🏪 *Update Store Name*\n\nPlease enter the new store display name (e.g., `iSwitch Electronics`):"
    await safe_edit_or_send(update, context, msg, reply_markup=kb)

async def prompt_contact_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verify_admin_access(update, context):
        return

    context.user_data["awaiting_setting_key"] = "contact_phone"
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅ Cancel", callback_data="adm_settings")]])
    msg = "📞 *Update Support Contact*\n\nPlease enter the phone number for customer inquiries (e.g., `0980632130`):"
    await safe_edit_or_send(update, context, msg, reply_markup=kb)

async def prompt_source_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verify_admin_access(update, context):
        return

    context.user_data["awaiting_setting_key"] = "channel_username"
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅ Cancel", callback_data="adm_settings")]])
    msg = "📢 *Update Source Channel*\n\nPlease enter the Telegram channel username (e.g., `@iSwitch0`):"
    await safe_edit_or_send(update, context, msg, reply_markup=kb)

async def view_payment_methods_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verify_admin_access(update, context):
        return

    methods = await get_payment_methods()
    text = "💳 *Configured Payment Methods*\n\n"
    for m in methods:
        text += (
            f"• *{m.get('name')}*\n"
            f"  Account Name: `{m.get('account_name')}`\n"
            f"  Account Number: `{m.get('account_number')}`\n"
            f"  Phone: `{m.get('phone')}`\n\n"
        )

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅ Back to Settings", callback_data="adm_settings")]
    ])
    await safe_edit_or_send(update, context, text, reply_markup=kb)

async def handle_setting_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    key = context.user_data.get("awaiting_setting_key")
    if not key:
        return False

    val = update.message.text.strip()

    # Security: Validate delivery_fee bounds
    if key == "delivery_fee":
        try:
            fee_num = float(val.replace(",", ""))
            if fee_num < 0 or fee_num > 100_000:
                await update.message.reply_text("❌ Delivery fee must be a valid positive amount between 0 and 100,000 ETB.")
                return True
            val = str(round(fee_num, 2))
        except ValueError:
            await update.message.reply_text("❌ Invalid delivery fee. Please enter a numeric amount (e.g., `150`):")
            return True

    context.user_data["awaiting_setting_key"] = None
    await set_setting(key, val)
    await log_admin_action(update.effective_user.id, "setting_updated", "setting", key, new_val=val)

    kb = InlineKeyboardMarkup([[InlineKeyboardButton("⚙️ Settings Menu", callback_data="adm_settings")]])
    await update.message.reply_text(f"✅ Setting *{key}* updated to: `{val}`", parse_mode="Markdown", reply_markup=kb)
    return True
