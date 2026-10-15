import logging
from telegram import Update
from telegram.ext import (
    Application, ApplicationBuilder, CommandHandler,
    CallbackQueryHandler, MessageHandler, ConversationHandler,
    filters, ContextTypes
)
from config import CUSTOMER_BOT_TOKEN
from customer_bot.handlers.start import start_command, main_menu_callback, help_callback, contact_callback
from customer_bot.handlers.catalog import (
    categories_menu, category_callback, pagination_callback,
    product_view, search_prompt, handle_text_search, browse_products,
    ask_about_product
)
from customer_bot.handlers.cart import (
    add_to_cart, view_cart, inc_cart_item, dec_cart_item,
    remove_cart_item, clear_cart
)
from customer_bot.handlers.checkout import (
    start_checkout, receive_unified_submission, receive_unified_text,
    receive_unified_location, receive_unified_contact, receive_receipt_upload,
    cancel_checkout, STATE_CHECKOUT
)
from customer_bot.handlers.orders import (
    my_orders_handler, order_detail_handler, prompt_reupload_receipt
)
from database.crud import get_customer_by_telegram_id, list_orders_for_customer

logger = logging.getLogger("iswitch.customer_bot")

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Exception in Customer Bot update handler:", exc_info=context.error)
    if isinstance(update, Update) and update.effective_chat:
        try:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="⚠️ An unexpected error occurred. Please try again or tap /start to refresh.",
                parse_mode="Markdown"
            )
        except Exception:
            pass

async def noop_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()

async def shop_all_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await browse_products(update, context, category_slug="all", page=1)

async def new_arrivals_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await browse_products(update, context, category_slug="new_arrivals", page=1)

async def offers_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await browse_products(update, context, category_slug="offers", page=1)

async def handle_customer_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Check if user was searching
    if context.user_data.get("awaiting_search"):
        handled = await handle_text_search(update, context)
        if handled:
            return

    # Check if user uploaded a receipt photo or document
    if update.message and (update.message.photo or update.message.document):
        if context.user_data.get("awaiting_standalone_receipt"):
            context.user_data["awaiting_standalone_receipt"] = False
            await receive_receipt_upload(update, context)
            return

        # Check if customer has a pending order awaiting receipt
        user = update.effective_user
        if user:
            cust = await get_customer_by_telegram_id(user.id)
            if cust:
                recent_orders = await list_orders_for_customer(cust["customer_id"], limit=3)
                pending_order = next((ro for ro in recent_orders if ro.get("order_status") in ["Pending", "Payment Pending"] or ro.get("payment_status") in ["Pending", "Rejected", "Uploaded"]), None)
                if pending_order:
                    context.user_data["current_order_id"] = pending_order["order_id"]
                    await receive_receipt_upload(update, context)
                    return

        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("📦 View My Orders", callback_data="cust_orders")]])
        await update.message.reply_text("ℹ️ To submit a payment receipt, please select your order from 📦 My Orders first:", reply_markup=kb)
        return

def create_customer_bot_app() -> Application:
    if not CUSTOMER_BOT_TOKEN:
        logger.warning("CUSTOMER_BOT_TOKEN is empty! Customer Bot cannot be initialized.")
        return None

    app = (
        ApplicationBuilder()
        .token(CUSTOMER_BOT_TOKEN)
        .connection_pool_size(8)
        .get_updates_connection_pool_size(4)
        .connect_timeout(30.0)
        .read_timeout(30.0)
        .write_timeout(30.0)
        .build()
    )

    # Checkout Conversation Handler (Single-screen unified checkout)
    checkout_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(start_checkout, pattern="^cart_checkout$"),
            CallbackQueryHandler(start_checkout, pattern="^buy_now_")
        ],
        states={
            STATE_CHECKOUT: [
                MessageHandler(filters.PHOTO | filters.Document.ALL, receive_unified_submission),
                MessageHandler(filters.LOCATION, receive_unified_location),
                MessageHandler(filters.CONTACT, receive_unified_contact),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_unified_text),
                CallbackQueryHandler(cancel_checkout, pattern="^chk_cancel$"),
                CallbackQueryHandler(start_checkout, pattern="^buy_now_")
            ]
        },
        fallbacks=[
            CallbackQueryHandler(cancel_checkout, pattern="^chk_cancel$"),
            CallbackQueryHandler(cancel_checkout, pattern="^cust_main$"),
            CallbackQueryHandler(cancel_checkout, pattern="^cust_cart$"),
            CommandHandler("start", start_command)
        ],
        allow_reentry=True
    )

    # Core Commands
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("orders", my_orders_handler))
    app.add_handler(CommandHandler("cart", view_cart))
    app.add_handler(CommandHandler("help", help_callback))

    # Add Checkout Conversation
    app.add_handler(checkout_conv)

    # Main Navigation Callbacks
    app.add_handler(CallbackQueryHandler(main_menu_callback, pattern="^cust_main$"))
    app.add_handler(CallbackQueryHandler(shop_all_callback, pattern="^cust_shop$"))
    app.add_handler(CallbackQueryHandler(categories_menu, pattern="^cust_categories$"))
    app.add_handler(CallbackQueryHandler(new_arrivals_callback, pattern="^cust_new$"))
    app.add_handler(CallbackQueryHandler(offers_callback, pattern="^cust_offers$"))
    app.add_handler(CallbackQueryHandler(search_prompt, pattern="^cust_search$"))
    app.add_handler(CallbackQueryHandler(view_cart, pattern="^cust_cart$"))
    app.add_handler(CallbackQueryHandler(my_orders_handler, pattern="^cust_orders$"))
    app.add_handler(CallbackQueryHandler(contact_callback, pattern="^cust_contact"))
    app.add_handler(CallbackQueryHandler(help_callback, pattern="^cust_help$"))
    app.add_handler(CallbackQueryHandler(noop_callback, pattern="^noop$"))

    # Catalog & Cart Callbacks
    app.add_handler(CallbackQueryHandler(category_callback, pattern="^cat_"))
    app.add_handler(CallbackQueryHandler(pagination_callback, pattern="^page_"))
    app.add_handler(CallbackQueryHandler(product_view, pattern="^prod_view_"))
    app.add_handler(CallbackQueryHandler(ask_about_product, pattern="^ask_prod_"))
    app.add_handler(CallbackQueryHandler(add_to_cart, pattern="^cart_add_"))
    app.add_handler(CallbackQueryHandler(inc_cart_item, pattern="^cart_inc_"))
    app.add_handler(CallbackQueryHandler(dec_cart_item, pattern="^cart_dec_"))
    app.add_handler(CallbackQueryHandler(remove_cart_item, pattern="^cart_rem_"))
    app.add_handler(CallbackQueryHandler(clear_cart, pattern="^cart_clear$"))

    # Orders & Standalone Receipt Callbacks
    app.add_handler(CallbackQueryHandler(order_detail_handler, pattern="^ord_view_"))
    app.add_handler(CallbackQueryHandler(prompt_reupload_receipt, pattern="^ord_upload_rcpt_"))

    # General Messages (Search and standalone receipts)
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_customer_message))

    # Error Handler
    app.add_error_handler(error_handler)

    return app
