import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from admin_bot.handlers.auth import verify_admin_access
from database.crud import list_orders_admin, get_order_by_id, update_delivery_status
from services.audit import log_admin_action
from services.notifier import notifier
from services.ui_utils import safe_edit_or_send

logger = logging.getLogger("iswitch.admin.deliveries")

async def deliveries_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verify_admin_access(update, context):
        return

    orders, total = await list_orders_admin(status="Out for Delivery", limit=10)
    if not orders:
        orders, total = await list_orders_admin(status="Preparing", limit=10)

    text = f"🚚 *Delivery & Dispatch Operations*\n\nActive Deliveries and Dispatches ({total} orders):"

    buttons = []
    for o in orders:
        num = o["order_number"]
        st = o["order_status"]
        city = o.get("delivery_city", "Addis Ababa")
        buttons.append([InlineKeyboardButton(f"🚚 {num} ({st}) - {city}", callback_data=f"adm_deliv_view_{o['order_id']}")])

    buttons.append([
        InlineKeyboardButton("📦 View All Orders", callback_data="adm_ords"),
        InlineKeyboardButton("🏠 Admin Menu", callback_data="adm_main")
    ])

    kb = InlineKeyboardMarkup(buttons)
    await safe_edit_or_send(update, context, text, reply_markup=kb)

async def delivery_detail_view(update: Update, context: ContextTypes.DEFAULT_TYPE, oid: int = None):
    if not await verify_admin_access(update, context):
        return

    query = update.callback_query
    if oid is None:
        if query and query.data:
            oid = int(query.data.replace("adm_deliv_view_", ""))
        else:
            return

    order = await get_order_by_id(oid)
    if not order:
        if query:
            await query.answer("Order not found.", show_alert=True)
        return

    deliv = order.get("delivery") or {}
    st = deliv.get("status", "Pending")

    lines = [
        f"🚚 *DELIVERY DISPATCH: Order #{order['order_number']}*\n",
        f"📍 *Destination:* {order.get('delivery_city', '')}, {order.get('delivery_area', '')}",
        f"🏠 *Address:* {order.get('delivery_address', 'N/A')}",
        f"👤 *Recipient:* {order.get('delivery_name', '')} ({order.get('delivery_phone', '')})",
        f"📊 *Current Status:* *{st}*",
        f"🏍 *Assigned Driver:* {deliv.get('delivery_person', 'Unassigned')}",
        f"📞 *Driver Phone:* {deliv.get('delivery_phone', 'N/A')}\n",
        "Tap below to change delivery status or assign courier:"
    ]

    lat = order.get("delivery_latitude")
    lng = order.get("delivery_longitude")
    rows = []
    if lat is not None and lng is not None:
        maps_link = f"https://maps.google.com/?q={lat},{lng}"
        rows.append([InlineKeyboardButton("🗺 Open Location in Google Maps", url=maps_link)])

    rows.extend([
        [
            InlineKeyboardButton("🏍 Assign Driver", callback_data=f"adm_deliv_assign_{oid}"),
            InlineKeyboardButton("🚚 Mark Out for Delivery", callback_data=f"adm_deliv_set_{oid}_Out for Delivery")
        ],
        [
            InlineKeyboardButton("✅ Mark Delivered", callback_data=f"adm_deliv_set_{oid}_Delivered"),
            InlineKeyboardButton("⚠️ Mark Failed/Returned", callback_data=f"adm_deliv_set_{oid}_Failed")
        ],
        [
            InlineKeyboardButton("⬅ Deliveries Menu", callback_data="adm_deliveries"),
            InlineKeyboardButton("👁 View Full Order", callback_data=f"adm_ord_view_{oid}")
        ]
    ])
    kb = InlineKeyboardMarkup(rows)

    await safe_edit_or_send(update, context, "\n".join(lines), reply_markup=kb)

async def prompt_assign_driver(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verify_admin_access(update, context):
        return

    query = update.callback_query
    oid = int(query.data.replace("adm_deliv_assign_", ""))
    context.user_data["assigning_driver_order_id"] = oid

    msg = (
        f"🏍 *Assign Courier for Order #{oid}*\n\n"
        "Please reply with the driver name and phone number separated by comma:\n"
        "_(e.g., Abebe Kebede, 0911223344)_"
    )
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅ Cancel", callback_data=f"adm_deliv_view_{oid}")]])
    await safe_edit_or_send(update, context, msg, reply_markup=kb)

async def handle_driver_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    oid = context.user_data.get("assigning_driver_order_id")
    if not oid:
        return False

    del context.user_data["assigning_driver_order_id"]
    text = update.message.text.strip()
    parts = [p.strip() for p in text.split(",") if p.strip()]
    driver_name = parts[0] if parts else "Delivery Courier"
    driver_phone = parts[1] if len(parts) > 1 else ""

    await update_delivery_status(oid, status="Out for Delivery", delivery_person=driver_name, delivery_phone=driver_phone)
    await log_admin_action(update.effective_user.id, "assign_driver", "delivery", oid, details=f"{driver_name} ({driver_phone})")

    order = await get_order_by_id(oid)
    if order and order.get("telegram_user_id"):
        await notifier.notify_customer_order_status(
            telegram_user_id=order["telegram_user_id"],
            order_number=order["order_number"],
            new_status="Out for Delivery",
            extra_msg=f"🚚 Your courier is {driver_name}" + (f" ({driver_phone})" if driver_phone else ""),
            order_id=oid
        )

    await update.message.reply_text(
        f"✅ Assigned driver *{driver_name}* to Order #{oid}!",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("👁 View Delivery", callback_data=f"adm_deliv_view_{oid}")]])
    )
    return True

async def set_delivery_status_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verify_admin_access(update, context):
        return

    query = update.callback_query
    # adm_deliv_set_{oid}_{status}
    remainder = query.data.replace("adm_deliv_set_", "")
    oid_str, new_status = remainder.split("_", 1)
    oid = int(oid_str)

    order = await get_order_by_id(oid)
    if not order:
        await query.answer("Order not found.", show_alert=True)
        return

    await update_delivery_status(oid, status=new_status)
    await log_admin_action(update.effective_user.id, "delivery_status_update", "delivery", oid, details=new_status)

    if order.get("telegram_user_id"):
        await notifier.notify_customer_order_status(
            telegram_user_id=order["telegram_user_id"],
            order_number=order["order_number"],
            new_status=new_status,
            extra_msg="Your shipment delivery status has been updated.",
            order_id=oid
        )

    await query.answer(f"Delivery status set to {new_status}!")
    await delivery_detail_view(update, context, oid=oid)
