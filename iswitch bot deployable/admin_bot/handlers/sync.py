import os
import json
import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from config import TELEGRAM_CHANNEL
from admin_bot.handlers.auth import verify_admin_access
from admin_bot.keyboards import admin_sync_panel_keyboard
from database.crud import get_sync_stats, get_setting
from services.importer import channel_importer
from services.audit import log_admin_action
from services.ui_utils import safe_edit_or_send

logger = logging.getLogger("iswitch.admin.sync")

active_import_task: asyncio.Task = None

async def sync_panel_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verify_admin_access(update, context):
        return

    db_stats = await get_sync_stats()
    channel = await get_setting("channel_username", TELEGRAM_CHANNEL)

    is_running = channel_importer.is_running
    is_paused = channel_importer.is_paused

    status_str = "🟢 Active (Synchronizing...)" if is_running else ("🟡 Paused" if is_paused else "⚪ Idle")

    text = (
        "🔄 *Telegram Channel Synchronization Panel*\n\n"
        f"📡 *Target Channel:* `{channel}`\n"
        f"⚡ *Current State:* *{status_str}*\n\n"
        "📊 *Cumulative Import Statistics:*\n"
        f"• Messages Scanned: *{db_stats['messages_scanned']}*\n"
        f"• Products Detected: *{db_stats['products_detected']}*\n"
        f"• Products Imported: *{db_stats['products_imported']}*\n"
        f"• Products Updated: *{db_stats['products_updated']}*\n"
        f"• Messages Skipped: *{db_stats['products_skipped']}*\n"
        f"• Needing Admin Review: ⚠️ *{db_stats['products_needing_review']}*\n"
        f"• Product Images Downloaded: 📸 *{db_stats['images_imported']}*\n"
        f"• Failed / Errors: ❌ *{db_stats['import_errors']}*\n\n"
        "All products are imported ONE BY ONE with strict non-hallucination and deduplication."
    )

    kb = admin_sync_panel_keyboard(is_running=is_running, is_paused=is_paused)
    await safe_edit_or_send(update, context, text, reply_markup=kb)

async def start_sync_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global active_import_task
    if not await verify_admin_access(update, context):
        return

    query = update.callback_query
    if channel_importer.is_running:
        await query.answer("Sync is already running!", show_alert=True)
        return

    admin_id = update.effective_user.id
    channel = await get_setting("channel_username", TELEGRAM_CHANNEL)
    channel_importer.channel_username = channel

    await log_admin_action(admin_id, "start_channel_sync", "channel", channel, details="Admin initiated channel import")

    # Start in background
    active_import_task = asyncio.create_task(channel_importer.import_from_web_pagination(max_pages=20, delay_seconds=0.8))

    await query.answer("▶ Channel Synchronization started!")
    await sync_panel_view(update, context)

async def pause_sync_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verify_admin_access(update, context):
        return
    query = update.callback_query
    channel_importer.pause()
    await log_admin_action(update.effective_user.id, "pause_channel_sync", "channel", channel_importer.channel_username)
    await query.answer("⏸ Sync paused.")
    await sync_panel_view(update, context)

async def resume_sync_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verify_admin_access(update, context):
        return
    query = update.callback_query
    channel_importer.resume()
    await log_admin_action(update.effective_user.id, "resume_channel_sync", "channel", channel_importer.channel_username)
    await query.answer("▶ Sync resumed.")
    await sync_panel_view(update, context)

async def cancel_sync_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verify_admin_access(update, context):
        return
    query = update.callback_query
    channel_importer.cancel()
    await log_admin_action(update.effective_user.id, "cancel_channel_sync", "channel", channel_importer.channel_username)
    await query.answer("⛔ Sync cancelled.")
    await sync_panel_view(update, context)

async def retry_sync_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verify_admin_access(update, context):
        return
    query = update.callback_query
    await query.answer("Retrying failed sync items...", show_alert=True)
    # Restart import to re-scan
    global active_import_task
    channel = await get_setting("channel_username", TELEGRAM_CHANNEL)
    channel_importer.channel_username = channel
    active_import_task = asyncio.create_task(channel_importer.import_from_web_pagination(max_pages=10, delay_seconds=0.5))
    await sync_panel_view(update, context)

async def prompt_json_export_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verify_admin_access(update, context):
        return

    context.user_data["awaiting_json_export"] = True

    kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅ Cancel", callback_data="adm_sync")]])
    text = (
        "📥 *Import Telegram Desktop JSON Export*\n\n"
        "You can import historical posts using Telegram Desktop:\n"
        "1. Open Telegram Desktop -> Go to @iSwitch0 channel\n"
        "2. Click ⋮ (Settings) -> Export chat history\n"
        "3. Select 'Machine-readable JSON' and photos\n"
        "4. Upload the generated `result.json` file here in chat!\n\n"
        "Please send the `result.json` file now:"
    )
    await safe_edit_or_send(update, context, text, reply_markup=kb)

async def handle_json_file_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("awaiting_json_export"):
        return False

    doc = update.message.document
    if not doc or not (doc.file_name and doc.file_name.endswith(".json")):
        await update.message.reply_text("Please upload a valid `.json` export file:")
        return True

    context.user_data["awaiting_json_export"] = False
    status_msg = await update.message.reply_text("⏳ Downloading and parsing JSON export file...")

    try:
        tg_file = await context.bot.get_file(doc.file_id)
        file_bytes = await tg_file.download_as_bytearray()
        data = json.loads(file_bytes.decode("utf-8", errors="replace"))

        messages = data.get("messages", [])
        await status_msg.edit_text(f"📦 Found {len(messages)} messages in file. Importing products...")

        imported = 0
        skipped = 0
        from services.importer import channel_importer
        for m in messages:
            if m.get("type") != "message":
                continue
            text = ""
            raw_text = m.get("text")
            if isinstance(raw_text, str):
                text = raw_text
            elif isinstance(raw_text, list):
                for part in raw_text:
                    if isinstance(part, str):
                        text += part
                    elif isinstance(part, dict) and "text" in part:
                        text += part["text"]

            if not text:
                continue

            msg_id = m.get("id")
            res = await channel_importer.import_single_message(
                message_id=msg_id,
                message_text=text,
                date_str=m.get("date"),
                media_file_name=m.get("photo") or m.get("file")
            )
            if res:
                imported += 1
            else:
                skipped += 1

        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 View Sync Panel", callback_data="adm_sync")],
            [InlineKeyboardButton("📦 Products Menu", callback_data="adm_prods")]
        ])
        await status_msg.edit_text(
            f"✅ *JSON Export Import Complete!*\n\n"
            f"• Products Processed: *{imported}*\n"
            f"• Skipped Non-Products: *{skipped}*",
            parse_mode="Markdown",
            reply_markup=kb
        )
        return True
    except Exception as e:
        logger.error(f"Error reading JSON export: {e}", exc_info=True)
        await status_msg.edit_text(f"❌ Failed to parse JSON export file: {e}")
        return True
