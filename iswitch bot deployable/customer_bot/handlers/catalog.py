import os
import logging
from pathlib import Path
from telegram import Update, InputMediaPhoto
from telegram.ext import ContextTypes
from config import MEDIA_DIR, TELEGRAM_CHANNEL
from database.crud import (
    get_all_categories, get_category_by_slug, list_products,
    get_product_by_id, get_product_images, update_product_image_telegram_id,
    add_product_image
)
from customer_bot.keyboards import (
    categories_keyboard, products_list_keyboard, product_detail_keyboard
)
from services.ui_utils import safe_edit_or_send
from services.importer import fetch_live_channel_photo

logger = logging.getLogger("iswitch.cust.catalog")

PAGE_SIZE = 8

async def categories_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cats = await get_all_categories(active_only=True)
    text = "📂 *Browse by Category*\n\nSelect a category to view available products:"
    await safe_edit_or_send(update, context, text, reply_markup=categories_keyboard(cats))

async def browse_products(update: Update, context: ContextTypes.DEFAULT_TYPE, category_slug: str = None, page: int = 1):
    query = update.callback_query
    if query:
        await query.answer()

    offset = (page - 1) * PAGE_SIZE
    
    # Query parameters
    cat_slug_param = category_slug if category_slug not in ["all", None] else None
    
    products, total = await list_products(
        category_slug=cat_slug_param,
        offset=offset,
        limit=PAGE_SIZE,
        admin_view=False
    )

    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    
    # Format Title
    title = "🛍 *All Products*"
    if category_slug and category_slug != "all":
        cat = await get_category_by_slug(category_slug)
        if cat:
            title = f"{cat.get('icon', '📂')} *{cat['name']}*"
        elif category_slug == "new_arrivals":
            title = "🔥 *New Arrivals*"
        elif category_slug == "offers":
            title = "🏷 *Special Offers & Discounts*"

    if not products:
        msg = f"{title}\n\nNo products found in this section right now. Please check back soon!"
        keyboard = categories_keyboard(await get_all_categories(active_only=True))
    else:
        msg = f"{title} (Showing {offset + 1}-{min(total, offset + len(products))} of {total}):\n\nSelect a product to view details & price:"
        keyboard = products_list_keyboard(products, page, total_pages, category_slug=category_slug)

    await safe_edit_or_send(update, context, text=msg, reply_markup=keyboard)

async def category_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    slug = query.data.replace("cat_", "")
    await browse_products(update, context, category_slug=slug, page=1)

async def pagination_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    # data: page_<slug>_<num>
    parts = query.data.split("_")
    page = int(parts[-1])
    slug = "_".join(parts[1:-1])
    await browse_products(update, context, category_slug=slug, page=page)

async def product_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    prod_id = int(query.data.replace("prod_view_", ""))
    prod = await get_product_by_id(prod_id)
    if not prod:
        await query.answer("Product not found or removed.", show_alert=True)
        return

    # Check cart quantity for this user
    user_cart = context.user_data.get("cart", {})
    in_cart_qty = user_cart.get(prod_id, {}).get("qty", 0)

    # Format Details
    name = prod["name"]
    price_val = prod.get("price") or 0
    disc_val = prod.get("discount_price")
    currency = prod.get("currency", "ETB")

    lines = [f"📱 *{name}*\n"]

    if prod.get("condition"):
        lines.append(f"✨ *Condition:* {prod['condition']}")
    if prod.get("storage"):
        lines.append(f"💾 *Storage:* {prod['storage']}")
    if prod.get("ram"):
        lines.append(f"⚡ *RAM:* {prod['ram']}")
    if prod.get("color"):
        lines.append(f"🎨 *Color:* {prod['color']}")
    if prod.get("battery_health"):
        lines.append(f"🔋 *Battery:* {prod['battery_health']}")

    if prod.get("description"):
        lines.append(f"📝 *Details:* {prod['description']}")

    # Price section
    if disc_val and disc_val < price_val:
        lines.append(f"\n💰 *Price:* ~{price_val:,.0f}~ *{disc_val:,.0f} {currency}* 🔥")
    elif price_val > 0:
        lines.append(f"\n💰 *Price:* *{price_val:,.0f} {currency}*")
    else:
        lines.append(f"\n💰 *Price:* Contact for price")

    # Availability & Stock
    avail = prod.get("availability", "Available")
    stock_qty = prod.get("stock_quantity")
    avail_emoji = "🟢" if avail == "Available" else ("🟡" if avail == "Low Stock" else "🔴")
    if stock_qty is not None and stock_qty > 0:
        lines.append(f"📦 *Stock:* {avail_emoji} {avail} ({stock_qty} left)")
    else:
        lines.append(f"📦 *Stock:* {avail_emoji} {avail}")

    caption = "\n".join(lines)
    keyboard = product_detail_keyboard(prod, in_cart_qty=in_cart_qty)

    # Images resolution & sending
    images = await get_product_images(prod_id)
    chat_id = update.effective_chat.id
    photo_sent = False

    # 1. Try sending from existing images records
    if images:
        for img in images:
            telegram_file_id = img.get("telegram_file_id")
            file_path = img.get("file_path")
            file_url = img.get("file_url")

            # 1a. Try cached Telegram File ID (instant, zero bandwidth)
            if telegram_file_id:
                try:
                    await context.bot.send_photo(
                        chat_id=chat_id,
                        photo=telegram_file_id,
                        caption=caption,
                        parse_mode="Markdown",
                        reply_markup=keyboard
                    )
                    photo_sent = True
                    break
                except Exception:
                    pass

            # 1b. Try local file path (check direct path, then MEDIA_DIR / filename)
            if file_path:
                target_file = Path(file_path)
                if not target_file.exists():
                    target_file = MEDIA_DIR / target_file.name
                if target_file.exists():
                    try:
                        with open(target_file, "rb") as pf:
                            sent_msg = await context.bot.send_photo(
                                chat_id=chat_id,
                                photo=pf,
                                caption=caption,
                                parse_mode="Markdown",
                                reply_markup=keyboard
                            )
                            photo_sent = True
                            if sent_msg.photo:
                                await update_product_image_telegram_id(img["image_id"], sent_msg.photo[-1].file_id)
                            break
                    except Exception as fe:
                        logger.warning(f"Error sending local photo {target_file}: {fe}")

            # 1c. Try file_url
            if file_url:
                try:
                    sent_msg = await context.bot.send_photo(
                        chat_id=chat_id,
                        photo=file_url,
                        caption=caption,
                        parse_mode="Markdown",
                        reply_markup=keyboard
                    )
                    photo_sent = True
                    if sent_msg.photo:
                        await update_product_image_telegram_id(img["image_id"], sent_msg.photo[-1].file_id)
                    break
                except Exception:
                    pass

    # 2. If photo not sent yet, auto-fetch LIVE channel photo on the fly!
    if not photo_sent and prod.get("source_message_id"):
        channel = prod.get("source_channel") or TELEGRAM_CHANNEL
        mid = prod.get("source_message_id")
        live_photo_url = await fetch_live_channel_photo(channel, mid)
        if live_photo_url:
            try:
                sent_msg = await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=live_photo_url,
                    caption=caption,
                    parse_mode="Markdown",
                    reply_markup=keyboard
                )
                photo_sent = True
                if sent_msg.photo:
                    cached_file_id = sent_msg.photo[-1].file_id
                    if images:
                        await update_product_image_telegram_id(images[0]["image_id"], cached_file_id)
                    else:
                        await add_product_image(
                            product_id=prod_id,
                            file_path="",
                            file_url=live_photo_url,
                            telegram_file_id=cached_file_id,
                            is_primary=1
                        )
            except Exception as le:
                logger.warning(f"Live photo fetch send failed for prod {prod_id}: {le}")

    # 3. Fallback to text message only if no photo was found or sent
    if not photo_sent:
        await context.bot.send_message(
            chat_id=chat_id,
            text=caption,
            parse_mode="Markdown",
            reply_markup=keyboard,
            disable_web_page_preview=True
        )

async def search_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    context.user_data["awaiting_search"] = True
    
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    cancel_kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅ Cancel", callback_data="cust_main")]])

    msg = (
        "🔎 *Search Products*\n\n"
        "Type phone model or name:\n"
        "_(e.g., iPhone 15, S24, Airpods)_"
    )
    await safe_edit_or_send(update, context, text=msg, reply_markup=cancel_kb)

async def ask_about_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    pid = int(query.data.replace("ask_prod_", ""))
    prod = await get_product_by_id(pid)
    name = prod["name"] if prod else f"Product #{pid}"
    price = prod.get("discount_price") or prod.get("price") or 0.0

    from database.crud import get_setting
    support_user = await get_setting("support_username", "israell0")
    phone = await get_setting("contact_phone", "0980632130")

    text = (
        f"💬 *Inquiry: {name}*\n"
        f"💰 Price: *{price:,.0f} ETB*\n\n"
        f"👤 Telegram: @{support_user.lstrip('@')}\n"
        f"📱 Phone: `{phone}`"
    )

    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 Chat with Admin", url=f"https://t.me/{support_user.lstrip('@')}")],
        [InlineKeyboardButton("⬅ Back to Product", callback_data=f"prod_view_{pid}")]
    ])

    await context.bot.send_message(chat_id=update.effective_chat.id, text=text, parse_mode="Markdown", reply_markup=kb)

async def handle_text_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("awaiting_search"):
        return False

    search_query = update.message.text.strip()
    context.user_data["awaiting_search"] = False

    products, total = await list_products(search=search_query, limit=PAGE_SIZE, offset=0, admin_view=False)
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)

    if not products:
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔎 Try Another Search", callback_data="cust_search")],
            [InlineKeyboardButton("🛍 Browse All", callback_data="cust_shop")],
            [InlineKeyboardButton("⬅ Main Menu", callback_data="cust_main")]
        ])
        await update.message.reply_text(
            f"🔎 No items found for '*{search_query}*'.\n\nTry another name or browse shop.",
            parse_mode="Markdown",
            reply_markup=kb
        )
        return True

    title = f"🔎 *Results for:* '_{search_query}_' ({total})"
    keyboard = products_list_keyboard(products, 1, total_pages, category_slug="all")
    await update.message.reply_text(
        text=f"{title}\n\nSelect a product:",
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    return True
