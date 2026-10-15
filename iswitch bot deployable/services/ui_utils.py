import logging
from telegram import Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

logger = logging.getLogger("iswitch.ui")

async def safe_edit_or_send(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    reply_markup=None,
    parse_mode: str = "Markdown",
    disable_web_page_preview: bool = True
):
    """
    Safely edits the current message if it is a text message,
    or sends a new message if it is a media message (photo/document/video)
    or if edit_message_text fails.
    Also gracefully handles markdown parsing errors and 'message not modified'.
    """
    query = update.callback_query
    if query:
        try:
            await query.answer()
        except Exception:
            pass

    chat_id = update.effective_chat.id if update.effective_chat else None
    if not chat_id:
        return

    if query and query.message:
        is_media = bool(
            query.message.photo
            or query.message.document
            or query.message.video
            or query.message.audio
            or query.message.voice
            or query.message.sticker
        )

        if not is_media:
            try:
                await query.edit_message_text(
                    text=text,
                    parse_mode=parse_mode,
                    reply_markup=reply_markup,
                    disable_web_page_preview=disable_web_page_preview
                )
                return
            except BadRequest as e:
                err_msg = str(e).lower()
                if "message is not modified" in err_msg:
                    return
                if "can't parse entities" in err_msg or "entity" in err_msg:
                    try:
                        await query.edit_message_text(
                            text=text,
                            parse_mode=None,
                            reply_markup=reply_markup,
                            disable_web_page_preview=disable_web_page_preview
                        )
                        return
                    except Exception:
                        pass
            except Exception:
                pass

    # Send a new message if editing was not possible or failed
    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=parse_mode,
            reply_markup=reply_markup,
            disable_web_page_preview=disable_web_page_preview
        )
    except BadRequest as e:
        err_msg = str(e).lower()
        if "can't parse entities" in err_msg or "entity" in err_msg:
            await context.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=None,
                reply_markup=reply_markup,
                disable_web_page_preview=disable_web_page_preview
            )
        else:
            logger.error(f"Failed to send message: {e}")
    except Exception as e:
        logger.error(f"Failed to send message: {e}")

async def safe_edit_caption_or_send(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    caption: str,
    reply_markup=None,
    parse_mode: str = "Markdown"
):
    """
    Safely edits the caption of a media message (photo/document/video) if possible.
    If caption exceeds 1024 chars or editing fails, sends a new message or edits text.
    """
    query = update.callback_query
    if query:
        try:
            await query.answer()
        except Exception:
            pass

    chat_id = update.effective_chat.id if update.effective_chat else None
    if not chat_id:
        return

    if query and query.message:
        is_media = bool(
            query.message.photo
            or query.message.document
            or query.message.video
        )

        if is_media and len(caption) <= 1024:
            try:
                await query.edit_message_caption(
                    caption=caption,
                    parse_mode=parse_mode,
                    reply_markup=reply_markup
                )
                return
            except BadRequest as e:
                err_msg = str(e).lower()
                if "message is not modified" in err_msg:
                    return
                if "can't parse entities" in err_msg or "entity" in err_msg:
                    try:
                        await query.edit_message_caption(
                            caption=caption,
                            parse_mode=None,
                            reply_markup=reply_markup
                        )
                        return
                    except Exception:
                        pass
            except Exception:
                pass

    # If media caption cannot be edited or it's a text message:
    await safe_edit_or_send(update, context, caption, reply_markup=reply_markup, parse_mode=parse_mode)

def escape_md(text: str) -> str:
    """Escapes Telegram Markdown V1 special characters in user input to prevent entity parsing errors."""
    if not text:
        return ""
    s = str(text)
    s = s.replace("\\", "\\\\")
    return s.replace("_", "\\_").replace("*", "\\*").replace("[", "\\[").replace("`", "'")

def format_admin_order_card(order: dict, title: str = "ORDER") -> str:
    """Formats an order into a clean, compact, mobile-optimized card for admins."""
    num = order.get("order_number", "N/A")
    raw_name = order.get("delivery_name") or order.get("customer_name") or "Customer"
    cust_name = escape_md(raw_name)
    raw_phone = order.get("delivery_phone") or order.get("customer_phone") or "N/A"
    phone = str(raw_phone).replace("`", "").strip()
    raw_tg = f"@{order['telegram_username']}" if order.get("telegram_username") else ""
    tg_user = escape_md(raw_tg)
    total = order.get("total", 0.0)
    currency = order.get("currency", "ETB")
    delivery_fee = order.get("delivery_fee", 150.0)
    pay_method = escape_md(order.get("payment_method") or "Bank Transfer")
    ord_st = order.get("order_status", "Pending")
    pay_st = order.get("payment_status", "Pending")

    status_badges = {
        "Pending": "🟡 Pending",
        "Payment Pending": "💳 Payment Pending",
        "Payment Confirmed": "✅ Payment Confirmed",
        "Preparing": "📦 Preparing",
        "Out for Delivery": "🚚 Out for Delivery",
        "Delivered": "🎉 Delivered",
        "Cancelled": "❌ Cancelled"
    }
    badge = status_badges.get(ord_st, ord_st)

    lines = [
        f"🛍️ *{title} #{num}*",
        "━━━━━━━━━━━━━━━━━━━━",
        f"👤 *Customer:* {cust_name}  |  📞 `{phone}`  {tg_user}".strip(),
    ]

    loc = f"{order.get('delivery_city', '')}, {order.get('delivery_area', '')}".strip(", ")
    addr = order.get("delivery_address") or ""
    landmark = order.get("delivery_landmark") or ""
    dest = loc
    if addr and addr != loc:
        dest += f" - {addr}" if dest else addr
    if landmark:
        dest += f" ({landmark})"
    if dest:
        lines.append(f"📍 *Delivery:* {escape_md(dest)}")

    items = order.get("items", [])
    if items:
        lines.append("\n🛒 *Items:*")
        for it in items:
            pname = escape_md(it.get("product_name") or "Product")
            qty = it.get("quantity") or 1
            tot = it.get("total_price") or 0.0
            lines.append(f"• {pname} ({qty}x) — {tot:,.0f} {currency}")

    receipts = order.get("receipts") or []
    rcpt_count = len(receipts) if receipts else (1 if pay_st == "Uploaded" else 0)
    rcpt_info = f"📎 {rcpt_count} slip(s)" if rcpt_count > 0 else "No slip"

    lines.extend([
        "━━━━━━━━━━━━━━━━━━━━",
        f"💰 *Total:* *{total:,.0f} {currency}* (Delivery: {delivery_fee:,.0f} {currency})",
        f"💳 *Payment:* *{pay_method}* ({pay_st} | {rcpt_info})",
        f"📊 *Status:* *{badge}*"
    ])

    if order.get("admin_notes"):
        lines.append(f"\n📝 *Notes:* {escape_md(order['admin_notes'])}")

    return "\n".join(lines)
