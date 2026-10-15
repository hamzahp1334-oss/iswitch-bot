import logging
from telegram import Update
from telegram.ext import (
    Application, ApplicationBuilder, CommandHandler,
    CallbackQueryHandler, MessageHandler, filters, ContextTypes
)
from config import ADMIN_BOT_TOKEN
from admin_bot.handlers.dashboard import admin_start, dashboard_view, reports_view
from admin_bot.handlers.products import (
    products_menu, list_products_handler, product_detail_admin,
    toggle_availability, toggle_featured, toggle_new_arrival,
    prompt_edit_price, handle_price_input, prompt_edit_discount,
    handle_discount_input, prompt_edit_stock, handle_stock_input,
    prompt_edit_category, set_product_category_callback,
    prompt_product_search, handle_product_search_input, prompt_add_product,
    delete_product_confirm, delete_product_execute,
    review_queue_view, review_queue_detail,
    handle_add_product_text_input, set_add_product_category_callback,
    set_add_product_condition_callback, set_add_product_qty_callback,
    set_add_product_storage_callback,
    skip_add_product_desc_callback, cancel_add_product_callback,
    skip_add_product_photo_callback, prompt_edit_product_photo,
    prompt_edit_condition, set_product_condition_callback,
    handle_admin_photo_upload
)
from admin_bot.handlers.orders import (
    orders_menu, payments_menu, orders_filter_handler, orders_pagination_handler,
    prompt_order_search, handle_order_search_input, order_view_admin,
    approve_payment_handler, reject_payment_prompt, quick_reject_callback,
    update_order_status_callback, handle_rejection_reason_input,
    prompt_order_notes, handle_order_notes_input, customer_call_info,
    view_receipt_photo_admin
)
from admin_bot.handlers.sync import (
    sync_panel_view, start_sync_callback, pause_sync_callback,
    resume_sync_callback, cancel_sync_callback, retry_sync_callback,
    prompt_json_export_upload, handle_json_file_upload
)
from admin_bot.handlers.customers import (
    customers_menu, customer_view_admin, prompt_customer_search,
    handle_customer_search_input
)
from admin_bot.handlers.deliveries import (
    deliveries_menu, delivery_detail_view, prompt_assign_driver,
    handle_driver_input, set_delivery_status_callback
)
from admin_bot.handlers.announcements import (
    announcements_menu, compose_prompt, handle_broadcast_text, execute_broadcast
)
from admin_bot.handlers.settings import (
    settings_menu, prompt_delivery_fee, prompt_store_info,
    prompt_contact_support, prompt_source_channel,
    view_payment_methods_admin, handle_setting_input
)
from admin_bot.handlers.audit import audit_logs_view
from admin_bot.handlers.auth import verify_admin_access

logger = logging.getLogger("iswitch.admin_bot")

async def admin_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Exception in Admin Bot update handler:", exc_info=context.error)
    if isinstance(update, Update) and update.effective_chat:
        try:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="⚠️ An administrative error occurred. Please check system logs.",
                parse_mode="Markdown"
            )
        except Exception:
            pass

async def handle_admin_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verify_admin_access(update, context):
        return

    # 1. Manual Add Product Wizard Input
    if await handle_add_product_text_input(update, context):
        return

    # 2. Order rejection reason
    if await handle_rejection_reason_input(update, context):
        return

    # 3. Order notes
    if await handle_order_notes_input(update, context):
        return

    # 4. Order search
    if await handle_order_search_input(update, context):
        return

    # 5. Delivery driver assignment
    if await handle_driver_input(update, context):
        return

    # 6. Product price
    if await handle_price_input(update, context):
        return

    # 7. Product discount
    if await handle_discount_input(update, context):
        return

    # 8. Product stock
    if await handle_stock_input(update, context):
        return

    # 9. Product search
    if await handle_product_search_input(update, context):
        return

    # 10. Customer search
    if await handle_customer_search_input(update, context):
        return

    # 11. Broadcast text
    if await handle_broadcast_text(update, context):
        return

    # 12. Store settings
    if await handle_setting_input(update, context):
        return

async def handle_admin_photo_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verify_admin_access(update, context):
        return

    # Photo upload for product
    if await handle_admin_photo_upload(update, context):
        return

async def handle_admin_document_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verify_admin_access(update, context):
        return

    # JSON export file upload
    if await handle_json_file_upload(update, context):
        return

def create_admin_bot_app() -> Application:
    if not ADMIN_BOT_TOKEN:
        logger.warning("ADMIN_BOT_TOKEN is empty! Admin Bot cannot be initialized.")
        return None

    app = (
        ApplicationBuilder()
        .token(ADMIN_BOT_TOKEN)
        .connection_pool_size(8)
        .get_updates_connection_pool_size(4)
        .connect_timeout(30.0)
        .read_timeout(30.0)
        .write_timeout(30.0)
        .build()
    )

    # Core Slash Commands
    app.add_handler(CommandHandler("start", admin_start))
    app.add_handler(CommandHandler("dashboard", dashboard_view))
    app.add_handler(CommandHandler("orders", orders_menu))
    app.add_handler(CommandHandler("products", products_menu))
    app.add_handler(CommandHandler("customers", customers_menu))
    app.add_handler(CommandHandler("deliveries", deliveries_menu))
    app.add_handler(CommandHandler("reports", reports_view))
    app.add_handler(CommandHandler("settings", settings_menu))

    # Main Navigation
    app.add_handler(CallbackQueryHandler(admin_start, pattern="^adm_main$"))
    app.add_handler(CallbackQueryHandler(dashboard_view, pattern="^adm_dash$"))
    app.add_handler(CallbackQueryHandler(reports_view, pattern="^adm_reports$"))
    app.add_handler(CallbackQueryHandler(audit_logs_view, pattern="^adm_audit_logs$"))

    # Products Callbacks
    app.add_handler(CallbackQueryHandler(products_menu, pattern="^adm_prods$"))
    app.add_handler(CallbackQueryHandler(list_products_handler, pattern="^adm_prod_list_"))
    app.add_handler(CallbackQueryHandler(prompt_add_product, pattern="^adm_prod_add$"))
    app.add_handler(CallbackQueryHandler(set_add_product_category_callback, pattern="^adm_addp_cat_"))
    app.add_handler(CallbackQueryHandler(set_add_product_condition_callback, pattern="^adm_addp_cond_"))
    app.add_handler(CallbackQueryHandler(set_add_product_qty_callback, pattern="^adm_addp_qty_"))
    app.add_handler(CallbackQueryHandler(set_add_product_storage_callback, pattern="^adm_addp_stor_"))
    app.add_handler(CallbackQueryHandler(skip_add_product_desc_callback, pattern="^adm_addp_desc_skip$"))
    app.add_handler(CallbackQueryHandler(cancel_add_product_callback, pattern="^adm_addp_cancel$"))
    app.add_handler(CallbackQueryHandler(skip_add_product_photo_callback, pattern="^adm_addp_photo_skip_"))
    app.add_handler(CallbackQueryHandler(prompt_edit_product_photo, pattern="^adm_pedt_photo_"))
    app.add_handler(CallbackQueryHandler(prompt_product_search, pattern="^adm_prod_search$"))
    app.add_handler(CallbackQueryHandler(product_detail_admin, pattern="^adm_pview_"))
    app.add_handler(CallbackQueryHandler(toggle_availability, pattern="^adm_ptog_(sold|avail)_"))
    app.add_handler(CallbackQueryHandler(toggle_featured, pattern="^adm_ptog_feat_"))
    app.add_handler(CallbackQueryHandler(toggle_new_arrival, pattern="^adm_ptog_arr_"))
    app.add_handler(CallbackQueryHandler(prompt_edit_price, pattern="^adm_pedt_price_"))
    app.add_handler(CallbackQueryHandler(prompt_edit_discount, pattern="^adm_pedt_disc_"))
    app.add_handler(CallbackQueryHandler(prompt_edit_stock, pattern="^adm_pedt_stock_"))
    app.add_handler(CallbackQueryHandler(prompt_edit_condition, pattern="^adm_pedt_cond_"))
    app.add_handler(CallbackQueryHandler(set_product_condition_callback, pattern="^adm_pcond_set_"))
    app.add_handler(CallbackQueryHandler(prompt_edit_category, pattern="^adm_pedt_cat_"))
    app.add_handler(CallbackQueryHandler(set_product_category_callback, pattern="^adm_pcat_set_"))
    app.add_handler(CallbackQueryHandler(delete_product_confirm, pattern="^adm_pdel_confirm_"))
    app.add_handler(CallbackQueryHandler(delete_product_execute, pattern="^adm_pdel_exec_"))
    app.add_handler(CallbackQueryHandler(review_queue_view, pattern="^adm_prod_review_queue$"))
    app.add_handler(CallbackQueryHandler(review_queue_detail, pattern="^adm_rev_msg_"))

    # Orders & Payments Callbacks
    app.add_handler(CallbackQueryHandler(orders_menu, pattern="^adm_ords$"))
    app.add_handler(CallbackQueryHandler(payments_menu, pattern="^adm_payments$"))
    app.add_handler(CallbackQueryHandler(orders_filter_handler, pattern="^adm_ord_flt_"))
    app.add_handler(CallbackQueryHandler(orders_pagination_handler, pattern="^adm_ord_pg_"))
    app.add_handler(CallbackQueryHandler(prompt_order_search, pattern="^adm_ord_search$"))
    app.add_handler(CallbackQueryHandler(order_view_admin, pattern="^adm_ord_view_"))
    app.add_handler(CallbackQueryHandler(approve_payment_handler, pattern="^adm_pay_appr_"))
    app.add_handler(CallbackQueryHandler(reject_payment_prompt, pattern="^adm_pay_rej_"))
    app.add_handler(CallbackQueryHandler(quick_reject_callback, pattern="^adm_pay_quickrej_"))
    app.add_handler(CallbackQueryHandler(update_order_status_callback, pattern="^adm_ord_st_"))
    app.add_handler(CallbackQueryHandler(prompt_order_notes, pattern="^adm_ord_notes_"))
    app.add_handler(CallbackQueryHandler(customer_call_info, pattern="^adm_call_"))
    app.add_handler(CallbackQueryHandler(view_receipt_photo_admin, pattern="^adm_rcpt_view_"))

    # Deliveries Callbacks
    app.add_handler(CallbackQueryHandler(deliveries_menu, pattern="^adm_deliveries$"))
    app.add_handler(CallbackQueryHandler(delivery_detail_view, pattern="^adm_deliv_view_"))
    app.add_handler(CallbackQueryHandler(prompt_assign_driver, pattern="^adm_deliv_assign_"))
    app.add_handler(CallbackQueryHandler(set_delivery_status_callback, pattern="^adm_deliv_set_"))

    # Customers Callbacks
    app.add_handler(CallbackQueryHandler(customers_menu, pattern="^adm_custs$"))
    app.add_handler(CallbackQueryHandler(prompt_customer_search, pattern="^adm_csearch$"))
    app.add_handler(CallbackQueryHandler(customer_view_admin, pattern="^adm_cview_"))

    # Sync Callbacks
    app.add_handler(CallbackQueryHandler(sync_panel_view, pattern="^adm_sync$"))
    app.add_handler(CallbackQueryHandler(start_sync_callback, pattern="^adm_sync_start$"))
    app.add_handler(CallbackQueryHandler(pause_sync_callback, pattern="^adm_sync_pause$"))
    app.add_handler(CallbackQueryHandler(resume_sync_callback, pattern="^adm_sync_resume$"))
    app.add_handler(CallbackQueryHandler(cancel_sync_callback, pattern="^adm_sync_cancel$"))
    app.add_handler(CallbackQueryHandler(retry_sync_callback, pattern="^adm_sync_retry$"))
    app.add_handler(CallbackQueryHandler(prompt_json_export_upload, pattern="^adm_sync_upload_json$"))

    # Broadcast Callbacks
    app.add_handler(CallbackQueryHandler(announcements_menu, pattern="^adm_broadcast$"))
    app.add_handler(CallbackQueryHandler(compose_prompt, pattern="^adm_bc_compose_"))
    app.add_handler(CallbackQueryHandler(execute_broadcast, pattern="^adm_bc_send_execute$"))

    # Settings Callbacks
    app.add_handler(CallbackQueryHandler(settings_menu, pattern="^adm_settings$"))
    app.add_handler(CallbackQueryHandler(prompt_delivery_fee, pattern="^adm_set_fee$"))
    app.add_handler(CallbackQueryHandler(prompt_store_info, pattern="^adm_set_info$"))
    app.add_handler(CallbackQueryHandler(prompt_contact_support, pattern="^adm_set_contact$"))
    app.add_handler(CallbackQueryHandler(prompt_source_channel, pattern="^adm_set_channel$"))
    app.add_handler(CallbackQueryHandler(view_payment_methods_admin, pattern="^adm_set_payments$"))

    # Messages
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_admin_text_message))
    app.add_handler(MessageHandler(filters.PHOTO, handle_admin_photo_message))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_admin_document_message))

    # Error Handler
    app.add_error_handler(admin_error_handler)

    return app
