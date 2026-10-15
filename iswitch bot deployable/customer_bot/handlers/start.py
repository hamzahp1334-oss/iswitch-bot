import logging
from telegram import Update
from telegram.ext import ContextTypes
from database.crud import get_or_create_customer, get_setting
from customer_bot.keyboards import main_menu_keyboard
from services.ui_utils import safe_edit_or_send

logger = logging.getLogger("iswitch.cust.start")

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    if not user:
        return

    # Upsert customer profile
    await get_or_create_customer(
        telegram_user_id=user.id,
        telegram_username=user.username,
        full_name=user.full_name
    )

    store_name = await get_setting("store_name", "iSwitch Store")
    first_name = user.first_name.replace("_", "\\_").replace("*", "\\*") if user.first_name else "there"
    welcome_text = (
        f"👋 *Welcome to {store_name}!* 🛍\n\n"
        f"Hi {first_name}! Brand new & clean used phones with fast delivery in Addis Ababa.\n\n"
        "Choose an option below:"
    )

    await safe_edit_or_send(
        update,
        context,
        text=welcome_text,
        reply_markup=main_menu_keyboard()
    )

async def main_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    store_name = await get_setting("store_name", "iSwitch Store")
    text = f"🛍 *{store_name}*\n\nSelect a section below:"
    await safe_edit_or_send(update, context, text, reply_markup=main_menu_keyboard())

async def help_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contact_phone = await get_setting("contact_phone", "0980632130")
    support_user = await get_setting("support_username", "israell0")

    help_text = (
        "ℹ️ *How to Order:*\n\n"
        "1. 🛍 Browse products & tap *Buy Now*\n"
        "2. 📍 Share location or type address\n"
        "3. 💳 Pay via Telebirr or CBE\n"
        "4. 📸 Upload receipt\n"
        "5. 🚚 Fast delivery to your door!\n\n"
        f"📞 *Support:* `{contact_phone}` | @{support_user}"
    )

    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🛍 Shop Now", callback_data="cust_shop")],
        [InlineKeyboardButton("⬅ Main Menu", callback_data="cust_main")]
    ])

    await safe_edit_or_send(update, context, text=help_text, reply_markup=keyboard)

async def contact_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contact_phone = await get_setting("contact_phone", "0980632130")
    support_user = await get_setting("support_username", "israell0")
    channel = await get_setting("channel_username", "@iSwitch0")

    contact_text = (
        "📞 *Contact Support*\n\n"
        f"💬 *Admin:* @{support_user}\n"
        f"📱 *Phone:* `{contact_phone}`\n"
        f"📢 *Channel:* {channel}\n"
        "📍 *Location:* Addis Ababa"
    )

    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 Chat with Admin", url=f"https://t.me/{support_user.lstrip('@')}")],
        [InlineKeyboardButton("📢 View Channel", url=f"https://t.me/{channel.lstrip('@')}")],
        [InlineKeyboardButton("⬅ Main Menu", callback_data="cust_main")]
    ])

    await safe_edit_or_send(update, context, text=contact_text, reply_markup=keyboard)
