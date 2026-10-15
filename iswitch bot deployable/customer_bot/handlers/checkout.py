import re
import os
import logging
import asyncio
import urllib.request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from database.crud import (
    get_customer_by_telegram_id, get_or_create_customer, update_customer_delivery_info,
    create_order, add_receipt, update_receipt_file_path, list_orders_for_customer,
    get_setting, get_payment_methods, get_order_by_id, get_product_by_id
)
from services.storage import storage_service
from services.notifier import notifier
from services.ui_utils import safe_edit_or_send, escape_md

logger = logging.getLogger("iswitch.cust.checkout")

# Unified Conversation State
STATE_CHECKOUT = 1

# Backwards-compatibility aliases
STATE_NAME = 1
STATE_PHONE = 2
STATE_CITY_AREA = 3
STATE_ADDRESS = 4
STATE_PAYMENT_METHOD = 5
STATE_RECEIPT = 6

def parse_order_details_text(text: str) -> dict:
    """
    Intelligently extracts phone number, customer name, and delivery address
    from freeform text, multiline messages, or photo captions.
    """
    if not text:
        return {}

    result = {}

    # 1. Extract phone number (Ethiopian mobile numbers: 09..., 07..., +2519..., +2517...)
    phone_pattern = r'(?:\+?251|0)?([79]\d{8})\b'
    phone_match = re.search(phone_pattern, text)
    if phone_match:
        result["phone"] = f"0{phone_match.group(1)}"
        # Remove phone from temporary text copy
        text_without_phone = text[:phone_match.start()] + " " + text[phone_match.end():]
    else:
        text_without_phone = text

    # 2. Check for labelled formats: Name: ..., Address: ..., Phone: ...
    name_match = re.search(r'(?:full\s*name|name|ስም)\s*[:=\-]\s*([^\n,]+)', text, re.IGNORECASE)
    if name_match:
        result["full_name"] = name_match.group(1).strip()

    addr_match = re.search(r'(?:address|addr|location|ቦታ|አድራሻ)\s*[:=\-]\s*([^\n]+)', text, re.IGNORECASE)
    if addr_match:
        result["address"] = addr_match.group(1).strip()

    # 3. If labelled formats were not present, parse remaining lines or comma segments
    if not result.get("full_name") or not result.get("address"):
        lines = [line.strip() for line in text_without_phone.split('\n') if line.strip()]
        if len(lines) == 1 and ',' in lines[0]:
            lines = [p.strip() for p in lines[0].split(',') if p.strip()]

        # Filter out label keywords
        filtered = []
        for l in lines:
            cleaned = re.sub(r'^(?:full\s*name|name|phone|address|addr|location|ስም|ስልክ|አድራሻ)\s*[:=\-]?\s*', '', l, flags=re.IGNORECASE).strip()
            if cleaned and not re.match(r'^(?:\+?251|0)?[79]\d{8}$', cleaned):
                filtered.append(cleaned)

        if filtered:
            if not result.get("full_name") and len(filtered) >= 1:
                result["full_name"] = filtered[0]
            if not result.get("address"):
                if len(filtered) >= 2:
                    result["address"] = ", ".join(filtered[1:])
                elif len(filtered) == 1 and result.get("full_name") != filtered[0]:
                    result["address"] = filtered[0]

    return result

async def start_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Displays the consolidated, single-screen order checkout:
    Shows items summary, total amount (incl. delivery), payment accounts,
    and asks for Name, Phone, Address, and Payment Receipt in ONE step.
    """
    query = update.callback_query
    if query:
        await query.answer()

    # If triggered by "buy_now_{pid}", add item to cart first!
    if query and query.data and query.data.startswith("buy_now_"):
        pid = int(query.data.replace("buy_now_", ""))
        prod = await get_product_by_id(pid)
        if prod:
            if prod.get("availability") not in ["Available", "Low Stock"]:
                await query.answer("Sorry, this item is currently unavailable.", show_alert=True)
                return ConversationHandler.END
            price = prod.get("discount_price") or prod.get("price") or 0.0
            if "cart" not in context.user_data:
                context.user_data["cart"] = {}
            context.user_data["cart"][pid] = {
                "product_id": pid,
                "name": prod["name"],
                "unit_price": price,
                "qty": 1
            }

    cart = context.user_data.get("cart", {})
    if not cart:
        text = "🛒 *Your cart is empty!* Please add products before checking out."
        await safe_edit_or_send(update, context, text=text)
        return ConversationHandler.END

    items = list(cart.values())
    subtotal = sum(it["unit_price"] * it["qty"] for it in items)
    delivery_fee_str = await get_setting("delivery_fee", "150")
    delivery_fee = float(delivery_fee_str) if delivery_fee_str.isdigit() else 150.0
    total = subtotal + delivery_fee

    context.user_data["checkout"] = {
        "items": items,
        "subtotal": subtotal,
        "delivery_fee": delivery_fee,
        "total": total
    }

    user = update.effective_user
    cust = await get_customer_by_telegram_id(user.id)

    # Check for previously saved details
    has_saved = False
    saved_name = user.full_name or ""
    saved_phone = ""
    saved_addr = ""

    if cust and cust.get("phone"):
        saved_name = cust.get("full_name") or user.full_name or "Customer"
        saved_phone = cust.get("phone")
        city = cust.get("city") or "Addis Ababa"
        area = cust.get("area") or ""
        addr = cust.get("address") or ""
        saved_addr = addr or (f"{city}, {area}" if area else city)

        context.user_data["checkout"]["full_name"] = saved_name
        context.user_data["checkout"]["phone"] = saved_phone
        context.user_data["checkout"]["city"] = city
        context.user_data["checkout"]["area"] = area
        context.user_data["checkout"]["address"] = saved_addr
        context.user_data["checkout"]["has_saved_details"] = True
        has_saved = True

    # Build items summary text
    items_lines = []
    for it in items:
        items_lines.append(f"• {it['name']} ({it['qty']}x) — {it['unit_price'] * it['qty']:,.0f} ETB")
    items_text = "\n".join(items_lines)

    # Payment transfer accounts
    methods = await get_payment_methods()
    methods_lines = []
    primary_method_name = "Telebirr / CBE"
    if methods:
        primary_method_name = methods[0].get("name", "Telebirr")
        for m in methods:
            m_name = m.get("name", "Payment")
            acc_num = m.get("account_number") or m.get("phone", "")
            acc_name = m.get("account_name", "")
            detail_str = f"`{acc_num}`" if acc_num else ""
            if acc_name:
                detail_str += f" ({acc_name})"
            methods_lines.append(f"• *{m_name}:* {detail_str}")
    else:
        methods_lines.append("• *Telebirr:* `0980632130` (Israel / iSwitch)")
        methods_lines.append("• *CBE:* `100023456789` (iSwitch Store)")

    methods_text = "\n".join(methods_lines)
    context.user_data["checkout"]["payment_method"] = primary_method_name

    # Unified prompt
    msg = (
        f"🛍️ *ORDER CHECKOUT*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🛒 *Items:*\n{items_text}\n"
        f"🚚 *Delivery:* {delivery_fee:,.0f} ETB\n"
        f"💰 *Total Due:* *{total:,.0f} ETB*\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"💳 *Transfer Payment To:*\n"
        f"{methods_text}\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📝 *Please send your details & upload receipt:*\n\n"
        f"1. *Full Name*\n"
        f"2. *Phone Number*\n"
        f"3. *Delivery Address*\n"
        f"4. *Receipt Screenshot / Photo*\n\n"
    )

    if has_saved and saved_phone and saved_addr:
        msg += (
            f"👤 *Your Saved Delivery Info:*\n"
            f"• *Name:* {saved_name}\n"
            f"• *Phone:* `{saved_phone}`\n"
            f"• *Address:* {saved_addr}\n\n"
            f"👉 If details are correct, simply *upload your payment receipt photo*!\n"
            f"_(Or type new details in the photo caption)_"
        )
    else:
        msg += (
            f"💡 *Easy Way:* Upload your payment receipt photo and write your "
            f"*Name, Phone, and Address* in the caption!"
        )

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Cancel Checkout", callback_data="chk_cancel")]
    ])

    await safe_edit_or_send(update, context, text=msg, reply_markup=kb)
    return STATE_CHECKOUT

async def receive_unified_submission(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles receipt image or document upload during unified checkout."""
    file_id = None
    download_file_id = None
    original_name = "receipt.jpg"
    file_size = 0
    is_photo = False

    if update.message.photo:
        is_photo = True
        full_res_photo = update.message.photo[-1]
        file_id = full_res_photo.file_id
        file_size = full_res_photo.file_size or 0
        original_name = "receipt.jpg"

        if len(update.message.photo) >= 3 and file_size > 200_000:
            download_file_id = update.message.photo[-2].file_id
        else:
            download_file_id = file_id
    elif update.message.document:
        doc = update.message.document
        file_id = doc.file_id
        download_file_id = file_id
        file_size = doc.file_size or 0
        original_name = doc.file_name or "receipt.pdf"
    else:
        await update.message.reply_text("Please upload an image screenshot (JPG, PNG) or document (PDF):")
        return STATE_CHECKOUT

    # Validate file format and size
    valid, err = storage_service.validate_receipt_file(original_name, file_size)
    if not valid:
        await update.message.reply_text(f"❌ {err}\nPlease upload a valid receipt:")
        return STATE_CHECKOUT

    # Check for caption
    caption = (update.message.caption or "").strip()
    if caption:
        parsed = parse_order_details_text(caption)
        chk = context.user_data.setdefault("checkout", {})
        if parsed.get("full_name"):
            chk["full_name"] = parsed["full_name"]
        if parsed.get("phone"):
            chk["phone"] = parsed["phone"]
        if parsed.get("address"):
            chk["address"] = parsed["address"]

    chk = context.user_data.get("checkout", {})
    user = update.effective_user
    full_name = chk.get("full_name") or (user.full_name if user else "Customer")
    phone = chk.get("phone")
    address = chk.get("address")

    # If details missing in session, retrieve saved customer delivery profile from database
    if (not phone or not address) and user:
        try:
            cust_db = await get_customer_by_telegram_id(user.id)
            if cust_db and cust_db.get("phone"):
                phone = phone or cust_db.get("phone")
                address = address or cust_db.get("address") or cust_db.get("city", "Addis Ababa")
                full_name = full_name or cust_db.get("full_name") or user.full_name or "Customer"
                chk["phone"] = phone
                chk["address"] = address
                chk["full_name"] = full_name
                context.user_data["checkout"] = chk
        except Exception as db_err:
            logger.warning(f"Error fetching saved profile: {db_err}")

    # If details are complete, finalize order immediately!
    if phone and address:
        chk["full_name"] = full_name
        return await _finalize_order(update, context, file_id, download_file_id, original_name, file_size, is_photo)

    # Otherwise, store the receipt in session and ask for missing details
    chk["receipt_file"] = {
        "file_id": file_id,
        "download_file_id": download_file_id,
        "original_name": original_name,
        "file_size": file_size,
        "is_photo": is_photo
    }

    missing = []
    if not phone:
        missing.append("• *Phone Number* (e.g., 0980632130)")
    if not address:
        missing.append("• *Delivery Address* (e.g., Bole near Edna Mall)")
    missing_str = "\n".join(missing)

    await update.message.reply_text(
        f"📸 *Receipt Received!*\n\n"
        f"To complete your order, please reply with your:\n"
        f"{missing_str}\n\n"
        f"_(Example: Abebe Kebede, 0980632130, Bole Edna Mall)_",
        parse_mode="Markdown"
    )
    return STATE_CHECKOUT

async def receive_unified_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles text input (name, phone, address) during unified checkout."""
    text = (update.message.text or "").strip()
    if not text:
        return STATE_CHECKOUT

    parsed = parse_order_details_text(text)
    chk = context.user_data.setdefault("checkout", {})

    if parsed.get("full_name"):
        chk["full_name"] = parsed["full_name"]
    if parsed.get("phone"):
        chk["phone"] = parsed["phone"]
    if parsed.get("address"):
        chk["address"] = parsed["address"]

    user = update.effective_user
    full_name = chk.get("full_name") or (user.full_name if user else "Customer")
    phone = chk.get("phone")
    address = chk.get("address")

    # Check if receipt was already uploaded
    rf = chk.get("receipt_file")
    if rf and phone and address:
        chk["full_name"] = full_name
        return await _finalize_order(
            update, context,
            rf["file_id"], rf["download_file_id"],
            rf["original_name"], rf["file_size"], rf["is_photo"]
        )

    # If receipt not uploaded yet, prompt for receipt
    if phone and address:
        await update.message.reply_text(
            f"✅ *Details Saved!*\n\n"
            f"👤 *Name:* {full_name}\n"
            f"📱 *Phone:* `{phone}`\n"
            f"📍 *Address:* {address}\n\n"
            f"📸 *Now please upload your payment receipt / screenshot to complete your order:*",
            parse_mode="Markdown"
        )
    else:
        missing = []
        if not phone:
            missing.append("• *Phone Number* (e.g., 0980632130)")
        if not address:
            missing.append("• *Delivery Address* (e.g., Bole near Edna Mall)")
        missing_str = "\n".join(missing)

        await update.message.reply_text(
            f"📝 *Details Received!*\n\n"
            f"Please provide your:\n"
            f"{missing_str}\n"
            f"And upload your *payment receipt screenshot*.",
            parse_mode="Markdown"
        )

    return STATE_CHECKOUT

async def receive_unified_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles location pin sharing during checkout."""
    if not update.message.location:
        return STATE_CHECKOUT

    lat = update.message.location.latitude
    lng = update.message.location.longitude
    maps_url = f"https://maps.google.com/?q={lat},{lng}"

    chk = context.user_data.setdefault("checkout", {})
    chk["latitude"] = lat
    chk["longitude"] = lng
    chk["maps_url"] = maps_url
    chk["city"] = "Addis Ababa"
    chk["address"] = f"GPS Pin: {maps_url}"

    rf = chk.get("receipt_file")
    phone = chk.get("phone")
    if rf and phone:
        return await _finalize_order(
            update, context,
            rf["file_id"], rf["download_file_id"],
            rf["original_name"], rf["file_size"], rf["is_photo"]
        )

    await update.message.reply_text(
        "📍 *Location Pin Received!*\n\n"
        "Please upload your *payment receipt screenshot* (or send your phone number if not yet provided):",
        parse_mode="Markdown"
    )
    return STATE_CHECKOUT

async def receive_unified_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles contact sharing during checkout."""
    if not update.message.contact:
        return STATE_CHECKOUT

    phone = update.message.contact.phone_number
    chk = context.user_data.setdefault("checkout", {})
    chk["phone"] = phone
    if update.message.contact.first_name:
        fn = update.message.contact.first_name
        ln = update.message.contact.last_name or ""
        chk["full_name"] = f"{fn} {ln}".strip()

    rf = chk.get("receipt_file")
    address = chk.get("address")
    if rf and address:
        return await _finalize_order(
            update, context,
            rf["file_id"], rf["download_file_id"],
            rf["original_name"], rf["file_size"], rf["is_photo"]
        )

    await update.message.reply_text(
        f"📱 *Phone Received:* `{phone}`\n\n"
        f"Please send your *Delivery Address* and upload your *Payment Receipt*:",
        parse_mode="Markdown"
    )
    return STATE_CHECKOUT

async def _finalize_order(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    file_id: str,
    download_file_id: str,
    original_name: str,
    file_size: int,
    is_photo: bool
) -> int:
    """Creates the order and receipt in the database, notifies admins, and confirms to customer."""
    try:
        user = update.effective_user
        cart = context.user_data.get("cart", {})
        chk = context.user_data.get("checkout", {})

        full_name = chk.get("full_name") or (user.full_name if user else "Customer")
        phone = chk.get("phone", "")
        address = chk.get("address", "Addis Ababa")
        city = chk.get("city", "Addis Ababa")
        area = chk.get("area", "")

        user_id = user.id if user else 0
        username = user.username if user else ""

        # Security: Ensure order is strictly tied to this verified Telegram user
        cust = await get_or_create_customer(user_id, username=username, full_name=full_name)
        cust_id = cust["customer_id"]

        # Re-verify products and prices directly against database
        items_to_process = list(cart.values()) if cart else chk.get("items", [])
        items_list = []
        for it in items_to_process:
            pid = it.get("product_id")
            prod = await get_product_by_id(pid) if pid else None
            if prod:
                price = prod.get("discount_price") or prod.get("price") or 0.0
                pname = prod["name"]
            else:
                price = float(it.get("unit_price", 0.0))
                pname = it.get("name", "Product")
            qty = max(1, min(99, int(it.get("quantity") or it.get("qty") or 1)))
            items_list.append({
                "product_id": pid,
                "product_name": pname,
                "unit_price": price,
                "quantity": qty
            })

        # Robust fallback so items_list is never empty
        if not items_list:
            items_list = [{
                "product_id": None,
                "product_name": "Store Item",
                "unit_price": float(chk.get("subtotal", 0.0)),
                "quantity": 1
            }]

        delivery_fee = float(chk.get("delivery_fee", 150.0))

        # Save to customer profile in DB
        try:
            await update_customer_delivery_info(
                telegram_user_id=user_id,
                full_name=full_name,
                phone=phone,
                city=city,
                area=area,
                address=address,
                landmark=chk.get("landmark", ""),
                latitude=chk.get("latitude"),
                longitude=chk.get("longitude")
            )
        except Exception as e:
            logger.warning(f"Failed to update customer delivery info: {e}")

        delivery_info = {
            "full_name": full_name,
            "phone": phone,
            "city": city,
            "area": area,
            "sub_city": chk.get("sub_city", ""),
            "address": address,
            "landmark": chk.get("landmark", ""),
            "note": chk.get("note", ""),
            "payment_method": chk.get("payment_method", "Bank Transfer / Telebirr"),
            "latitude": chk.get("latitude"),
            "longitude": chk.get("longitude")
        }

        # Create Order in DB
        order = await create_order(
            customer_id=cust_id,
            items=items_list,
            delivery_info=delivery_info,
            delivery_fee=delivery_fee
        )

        # Add Receipt Record
        payment = order.get("payment")
        pay_id = payment["payment_id"] if payment else None

        receipt_id = await add_receipt(
            order_id=order["order_id"],
            customer_id=cust_id,
            payment_id=pay_id,
            file_path="",
            file_type="image/jpeg" if is_photo else "application/pdf",
            file_size=file_size,
            telegram_file_id=file_id
        )

        # Simple Confirmation to Customer - NEVER send receipt back to customer!
        conf_text = (
            f"✅ *Your order is under review*\n\n"
            f"🔢 *Order:* `#{order['order_number']}`\n"
            f"💰 *Total:* *{order['total']:,.0f} ETB*\n"
            f"👤 *Deliver to:* {escape_md(full_name)} (`{phone}`)\n"
            f"📍 *Address:* {escape_md(address)}\n\n"
            f"Thank you! We have received your order details and payment receipt. "
            f"We will notify you once verified."
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📦 My Orders", callback_data="cust_orders"),
             InlineKeyboardButton("🛍 Shop More", callback_data="cust_shop")]
        ])
        try:
            if update.message:
                await update.message.reply_text(conf_text, parse_mode="Markdown", reply_markup=kb)
            elif update.effective_chat:
                await context.bot.send_message(chat_id=update.effective_chat.id, text=conf_text, parse_mode="Markdown", reply_markup=kb)
        except Exception:
            if update.message:
                await update.message.reply_text(conf_text, parse_mode=None, reply_markup=kb)
            elif update.effective_chat:
                await context.bot.send_message(chat_id=update.effective_chat.id, text=conf_text, parse_mode=None, reply_markup=kb)

        # Clear user state
        context.user_data.pop("cart", None)
        context.user_data.pop("checkout", None)
        context.user_data.pop("current_order_id", None)
        context.user_data.pop("awaiting_standalone_receipt", None)

        # Fast download for admin local file preview
        saved_path = None
        try:
            tg_file = await asyncio.wait_for(context.bot.get_file(download_file_id), timeout=3.0)
            file_url = tg_file.file_path

            def _fetch_file(url):
                req = urllib.request.Request(url, headers={"User-Agent": "iSwitchStoreBot/1.0"})
                with urllib.request.urlopen(req, timeout=3.5) as resp:
                    return resp.read()

            file_bytes = await asyncio.wait_for(asyncio.to_thread(_fetch_file, file_url), timeout=4.0)
            saved_info = await storage_service.save_receipt(
                file_bytes=bytes(file_bytes),
                original_filename=original_name,
                order_id=order["order_id"],
                customer_id=cust_id
            )
            saved_path = saved_info["file_path"]
            await update_receipt_file_path(receipt_id, saved_path)
        except Exception as dl_err:
            logger.info(f"Fast local receipt download deferred: {dl_err}")

        # Instant Admin Notification via Admin Bot
        try:
            full_order = await get_order_by_id(order["order_id"])
            await notifier.notify_admins_receipt_uploaded(
                order=full_order or order,
                receipt_path=saved_path,
                telegram_file_id=file_id,
                is_photo=is_photo
            )
        except Exception as notif_err:
            logger.error(f"Error sending admin receipt notification: {notif_err}", exc_info=True)

        # Background downloader fallback if not yet saved to disk
        if not saved_path and cust:
            asyncio.create_task(
                _background_receipt_downloader(
                    bot=context.bot,
                    file_id=download_file_id,
                    original_name=original_name,
                    order_id=order["order_id"],
                    customer_id=cust_id,
                    receipt_id=receipt_id
                )
            )

        return ConversationHandler.END

    except Exception as e:
        logger.error(f"Critical error in _finalize_order: {e}", exc_info=True)
        fallback_msg = (
            "✅ *Your order is under review*\n\n"
            "We have received your payment receipt and order details. "
            "Our team is verifying it now. You can check status anytime in *📦 My Orders*."
        )
        try:
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("📦 My Orders", callback_data="cust_orders")]
            ])
            if update.message:
                await update.message.reply_text(fallback_msg, parse_mode="Markdown", reply_markup=kb)
            elif update.effective_chat:
                await context.bot.send_message(chat_id=update.effective_chat.id, text=fallback_msg, parse_mode="Markdown", reply_markup=kb)
        except Exception:
            pass
        return ConversationHandler.END

async def _background_receipt_downloader(bot, file_id: str, original_name: str, order_id: int, customer_id: int, receipt_id: int):
    """Downloads receipt in background without blocking customer checkout or admin notification."""
    try:
        tg_file = await bot.get_file(file_id)
        file_url = tg_file.file_path

        def _fetch():
            req = urllib.request.Request(file_url, headers={"User-Agent": "iSwitchStoreBot/1.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read()

        file_bytes = await asyncio.to_thread(_fetch)
        saved_info = await storage_service.save_receipt(
            file_bytes=bytes(file_bytes),
            original_filename=original_name,
            order_id=order_id,
            customer_id=customer_id
        )
        await update_receipt_file_path(receipt_id, saved_info["file_path"])
        logger.info(f"Background receipt download completed for order #{order_id}: {saved_info['file_path']}")
    except Exception as e:
        logger.warning(f"Background receipt download deferred or failed for order #{order_id}: {e}")

async def receive_receipt_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fallback handler for standalone receipt upload (e.g. from My Orders)."""
    user = update.effective_user
    cust = await get_customer_by_telegram_id(user.id)
    order_id = context.user_data.get("current_order_id")

    if not order_id and cust:
        recent_orders = await list_orders_for_customer(cust["customer_id"], limit=3)
        for ro in recent_orders:
            if ro.get("order_status") in ["Pending", "Payment Pending"] or ro.get("payment_status") in ["Pending", "Rejected", "Uploaded"]:
                order_id = ro["order_id"]
                break

    if not order_id:
        await update.message.reply_text("No active order awaiting receipt. View your orders via 📦 My Orders.")
        return ConversationHandler.END

    order = await get_order_by_id(order_id)
    if not order:
        await update.message.reply_text("Order not found.")
        return ConversationHandler.END

    # Security: Verify that the customer owns this order
    if not cust or order.get("customer_id") != cust["customer_id"]:
        await update.message.reply_text("⛔ Access denied: You do not own this order.")
        return ConversationHandler.END

    file_id = None
    download_file_id = None
    original_name = "receipt.jpg"
    file_size = 0
    is_photo = False

    if update.message.photo:
        is_photo = True
        full_res_photo = update.message.photo[-1]
        file_id = full_res_photo.file_id
        file_size = full_res_photo.file_size or 0
        original_name = "receipt.jpg"

        if len(update.message.photo) >= 3 and file_size > 200_000:
            download_file_id = update.message.photo[-2].file_id
        else:
            download_file_id = file_id
    elif update.message.document:
        doc = update.message.document
        file_id = doc.file_id
        download_file_id = file_id
        file_size = doc.file_size or 0
        original_name = doc.file_name or "receipt.pdf"
    else:
        await update.message.reply_text("Please upload an image screenshot or document:")
        return STATE_CHECKOUT

    valid, err = storage_service.validate_receipt_file(original_name, file_size)
    if not valid:
        await update.message.reply_text(f"❌ {err}\nPlease upload a valid file:")
        return STATE_CHECKOUT

    payment = order.get("payment")
    pay_id = payment["payment_id"] if payment else None

    receipt_id = await add_receipt(
        order_id=order_id,
        customer_id=cust["customer_id"] if cust else 1,
        payment_id=pay_id,
        file_path="",
        file_type="image/jpeg" if is_photo else "application/pdf",
        file_size=file_size,
        telegram_file_id=file_id
    )

    # Simple confirmation to customer - NEVER send receipt back to customer!
    conf_text = (
        f"✅ *Your order is under review*\n\n"
        f"🔢 *Order:* `#{order['order_number']}`\n"
        f"Status: 🟡 *Verifying Payment*\n\n"
        f"We have received your payment receipt. We will notify you once verified!"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📦 My Orders", callback_data="cust_orders"),
         InlineKeyboardButton("🛍 Shop More", callback_data="cust_shop")]
    ])
    try:
        await update.message.reply_text(conf_text, parse_mode="Markdown", reply_markup=kb)
    except Exception:
        await update.message.reply_text(conf_text, parse_mode=None, reply_markup=kb)

    context.user_data.pop("cart", None)
    context.user_data.pop("current_order_id", None)
    context.user_data.pop("awaiting_standalone_receipt", None)

    saved_path = None
    try:
        tg_file = await asyncio.wait_for(context.bot.get_file(download_file_id), timeout=3.0)
        file_url = tg_file.file_path

        def _fetch_file(url):
            req = urllib.request.Request(url, headers={"User-Agent": "iSwitchStoreBot/1.0"})
            with urllib.request.urlopen(req, timeout=3.5) as resp:
                return resp.read()

        file_bytes = await asyncio.wait_for(asyncio.to_thread(_fetch_file, file_url), timeout=4.0)
        saved_info = await storage_service.save_receipt(
            file_bytes=bytes(file_bytes),
            original_filename=original_name,
            order_id=order_id,
            customer_id=cust["customer_id"] if cust else 1
        )
        saved_path = saved_info["file_path"]
        await update_receipt_file_path(receipt_id, saved_path)
    except Exception as dl_err:
        logger.info(f"Fast local receipt download skipped/deferred: {dl_err}")

    # Instant Admin Notification via Admin Bot
    try:
        full_order = await get_order_by_id(order_id)
        await notifier.notify_admins_receipt_uploaded(
            order=full_order or order,
            receipt_path=saved_path,
            telegram_file_id=file_id,
            is_photo=is_photo
        )
    except Exception as notif_err:
        logger.error(f"Error sending admin receipt notification: {notif_err}", exc_info=True)

    if not saved_path and cust:
        asyncio.create_task(
            _background_receipt_downloader(
                bot=context.bot,
                file_id=download_file_id,
                original_name=original_name,
                order_id=order_id,
                customer_id=cust["customer_id"],
                receipt_id=receipt_id
            )
        )

    return ConversationHandler.END

async def cancel_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer("Checkout cancelled.")
    context.user_data.pop("checkout", None)
    await safe_edit_or_send(update, context, text="Checkout cancelled. Items remain in your cart.")
    return ConversationHandler.END

# Backwards compatibility handlers (in case any old callbacks are invoked)
async def use_saved_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await start_checkout(update, context)

async def enter_new_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await start_checkout(update, context)

async def receive_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await receive_unified_text(update, context)

async def receive_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message and update.message.contact:
        return await receive_unified_contact(update, context)
    return await receive_unified_text(update, context)

async def receive_city_area(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message and update.message.location:
        return await receive_unified_location(update, context)
    return await receive_unified_text(update, context)

async def receive_address(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message and update.message.location:
        return await receive_unified_location(update, context)
    return await receive_unified_text(update, context)

async def present_payment_methods(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await start_checkout(update, context)

async def receive_payment_method(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await start_checkout(update, context)
