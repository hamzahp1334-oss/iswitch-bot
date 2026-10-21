from telegram import InlineKeyboardButton, InlineKeyboardMarkup

def admin_main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Dashboard", callback_data="adm_dash"), InlineKeyboardButton("📦 Products", callback_data="adm_prods")],
        [InlineKeyboardButton("🛒 Orders", callback_data="adm_ords"), InlineKeyboardButton("💳 Payments", callback_data="adm_payments")],
        [InlineKeyboardButton("👥 Customers", callback_data="adm_custs"), InlineKeyboardButton("🚚 Deliveries", callback_data="adm_deliveries")],
        [InlineKeyboardButton("🔄 Sync Channel", callback_data="adm_sync"), InlineKeyboardButton("📢 Broadcast", callback_data="adm_broadcast")],
        [InlineKeyboardButton("📈 Reports", callback_data="adm_reports"), InlineKeyboardButton("⚙️ Settings", callback_data="adm_settings")],
        [InlineKeyboardButton("📋 Audit Logs", callback_data="adm_audit_logs")]
    ])

def admin_products_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Browse Catalog", callback_data="adm_prod_list_1"), InlineKeyboardButton("➕ Add Product", callback_data="adm_prod_add")],
        [InlineKeyboardButton("⚠️ Review Queue (Pending)", callback_data="adm_prod_review_queue")],
        [InlineKeyboardButton("🔎 Search Product", callback_data="adm_prod_search"), InlineKeyboardButton("🏠 Admin Menu", callback_data="adm_main")]
    ])

def admin_products_list_keyboard(products: list, page: int, total_pages: int) -> InlineKeyboardMarkup:
    buttons = []
    for p in products:
        status_ico = "🟢" if p.get("availability") == "Available" else ("🔴" if p.get("availability") == "Sold" else "🟡")
        price = p.get('discount_price') or p.get('price') or 0
        name = p['name'][:22]
        title = f"{status_ico} {name} - {price:,.0f} ETB"
        buttons.append([InlineKeyboardButton(title, callback_data=f"adm_pview_{p['product_id']}")])

    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton("⬅ Prev", callback_data=f"adm_prod_list_{page - 1}"))
    nav.append(InlineKeyboardButton(f"{page}/{max(1, total_pages)}", callback_data="noop"))
    if page < total_pages:
        nav.append(InlineKeyboardButton("Next ➡", callback_data=f"adm_prod_list_{page + 1}"))
    if nav:
        buttons.append(nav)

    buttons.append([
        InlineKeyboardButton("➕ Add Product", callback_data="adm_prod_add"),
        InlineKeyboardButton("🔎 Search", callback_data="adm_prod_search"),
        InlineKeyboardButton("⬅ Products Menu", callback_data="adm_prods")
    ])
    return InlineKeyboardMarkup(buttons)

def admin_product_detail_keyboard(product: dict) -> InlineKeyboardMarkup:
    pid = product["product_id"]
    avail = product.get("availability", "Available")
    feat = product.get("featured", 0)
    new_arr = product.get("new_arrival", 0)

    toggle_avail_txt = "🔴 Mark Sold" if avail == "Available" else "🟢 Mark Available"
    toggle_avail_cb = f"adm_ptog_sold_{pid}" if avail == "Available" else f"adm_ptog_avail_{pid}"

    feat_txt = "⭐ Unfeature" if feat else "⭐ Feature"
    arr_txt = "🔥 Remove New" if new_arr else "🔥 Mark New"

    buttons = [
        [
            InlineKeyboardButton("💰 Edit Price", callback_data=f"adm_pedt_price_{pid}"),
            InlineKeyboardButton("🏷 Set Discount", callback_data=f"adm_pedt_disc_{pid}")
        ],
        [
            InlineKeyboardButton("📦 Edit Stock", callback_data=f"adm_pedt_stock_{pid}"),
            InlineKeyboardButton("✨ Edit Condition", callback_data=f"adm_pedt_cond_{pid}")
        ],
        [
            InlineKeyboardButton(toggle_avail_txt, callback_data=toggle_avail_cb),
            InlineKeyboardButton(feat_txt, callback_data=f"adm_ptog_feat_{pid}")
        ],
        [
            InlineKeyboardButton(arr_txt, callback_data=f"adm_ptog_arr_{pid}"),
            InlineKeyboardButton("📁 Change Category", callback_data=f"adm_pedt_cat_{pid}")
        ],
        [
            InlineKeyboardButton("📸 Add / Change Photo", callback_data=f"adm_pedt_photo_{pid}"),
            InlineKeyboardButton("🗑 Delete Product", callback_data=f"adm_pdel_confirm_{pid}")
        ]
    ]

    if product.get("source_message_url"):
        buttons.append([InlineKeyboardButton("🔗 Open Telegram Post", url=product["source_message_url"])])

    buttons.append([
        InlineKeyboardButton("⬅ Back to Products", callback_data="adm_prod_list_1"),
        InlineKeyboardButton("🏠 Admin Menu", callback_data="adm_main")
    ])
    return InlineKeyboardMarkup(buttons)

def admin_orders_keyboard(orders: list, current_filter: str, page: int, total_pages: int) -> InlineKeyboardMarkup:
    buttons = []

    # Quick Status Filter Bar
    buttons.append([
        InlineKeyboardButton("🟡 Pending", callback_data="adm_ord_flt_Pending"),
        InlineKeyboardButton("💳 Pay Pending", callback_data="adm_ord_flt_Payment Pending"),
        InlineKeyboardButton("✅ Confirmed", callback_data="adm_ord_flt_Payment Confirmed")
    ])
    buttons.append([
        InlineKeyboardButton("📦 Preparing", callback_data="adm_ord_flt_Preparing"),
        InlineKeyboardButton("🚚 Out for Delivery", callback_data="adm_ord_flt_Out for Delivery"),
        InlineKeyboardButton("📋 All", callback_data="adm_ord_flt_All")
    ])

    for o in orders:
        status_icons = {
            "Pending": "🟡",
            "Payment Pending": "💳",
            "Payment Confirmed": "✅",
            "Preparing": "📦",
            "Out for Delivery": "🚚",
            "Delivered": "🎉",
            "Cancelled": "❌"
        }
        ico = status_icons.get(o["order_status"], "📋")
        num = o["order_number"]
        cust = (o.get("customer_name") or o.get("delivery_name") or "")[:12]
        tot = f"{o['total']:,.0f} ETB"
        buttons.append([InlineKeyboardButton(f"{ico} {num} | {cust} | {tot}", callback_data=f"adm_ord_view_{o['order_id']}")])

    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton("⬅ Prev", callback_data=f"adm_ord_pg_{current_filter}_{page - 1}"))
    nav.append(InlineKeyboardButton(f"{page}/{max(1, total_pages)}", callback_data="noop"))
    if page < total_pages:
        nav.append(InlineKeyboardButton("Next ➡", callback_data=f"adm_ord_pg_{current_filter}_{page + 1}"))
    if nav:
        buttons.append(nav)

    buttons.append([
        InlineKeyboardButton("🔎 Search Order", callback_data="adm_ord_search"),
        InlineKeyboardButton("🏠 Admin Menu", callback_data="adm_main")
    ])
    return InlineKeyboardMarkup(buttons)

def admin_order_detail_keyboard(order: dict) -> InlineKeyboardMarkup:
    oid = order["order_id"]
    ord_status = order.get("order_status", "Pending")
    pay_status = order.get("payment_status", "Pending")

    buttons = []

    # Row 1: Contextual Primary Action based on current workflow stage
    if pay_status in ["Pending", "Uploaded"] and ord_status in ["Pending", "Payment Pending"]:
        buttons.append([
            InlineKeyboardButton("✅ Approve Payment", callback_data=f"adm_pay_appr_{oid}"),
            InlineKeyboardButton("❌ Reject Payment", callback_data=f"adm_pay_rej_{oid}")
        ])
    elif ord_status == "Payment Confirmed":
        buttons.append([
            InlineKeyboardButton("📦 Mark Preparing", callback_data=f"adm_ord_st_{oid}_Preparing"),
            InlineKeyboardButton("🚚 Out for Delivery", callback_data=f"adm_ord_st_{oid}_Out for Delivery")
        ])
    elif ord_status == "Preparing":
        buttons.append([
            InlineKeyboardButton("🚚 Out for Delivery", callback_data=f"adm_ord_st_{oid}_Out for Delivery"),
            InlineKeyboardButton("🎉 Mark Delivered", callback_data=f"adm_ord_st_{oid}_Delivered")
        ])
    elif ord_status == "Out for Delivery":
        buttons.append([
            InlineKeyboardButton("🎉 Mark Delivered", callback_data=f"adm_ord_st_{oid}_Delivered"),
            InlineKeyboardButton("❌ Cancel Order", callback_data=f"adm_ord_st_{oid}_Cancelled")
        ])
    elif ord_status in ["Delivered", "Cancelled"]:
        buttons.append([
            InlineKeyboardButton("🔄 Re-open (Preparing)", callback_data=f"adm_ord_st_{oid}_Preparing")
        ])
    else:
        buttons.append([
            InlineKeyboardButton("📦 Mark Preparing", callback_data=f"adm_ord_st_{oid}_Preparing"),
            InlineKeyboardButton("🚚 Out for Delivery", callback_data=f"adm_ord_st_{oid}_Out for Delivery")
        ])

    # Row 2: Direct Tools (All in 1 compact row)
    tools = []
    receipts = order.get("receipts") or []
    if receipts or pay_status == "Uploaded" or order.get("payment_receipt_path"):
        tools.append(InlineKeyboardButton("📸 Receipt", callback_data=f"adm_rcpt_view_{oid}"))

    tg_uid = order.get("telegram_user_id")
    if tg_uid:
        tools.append(InlineKeyboardButton("💬 Chat", url=f"tg://user?id={tg_uid}"))
    else:
        tools.append(InlineKeyboardButton("📞 Call", callback_data=f"adm_call_{oid}"))

    lat = order.get("delivery_latitude")
    lng = order.get("delivery_longitude")
    if lat is not None and lng is not None:
        tools.append(InlineKeyboardButton("🗺 Map", url=f"https://maps.google.com/?q={lat},{lng}"))

    if tools:
        buttons.append(tools)

    # Row 3: Navigation & Secondary Action
    if ord_status in ["Payment Confirmed", "Preparing"]:
        buttons.append([
            InlineKeyboardButton("❌ Cancel Order", callback_data=f"adm_ord_st_{oid}_Cancelled"),
            InlineKeyboardButton("⬅ Back to Orders", callback_data="adm_ords")
        ])
    else:
        buttons.append([
            InlineKeyboardButton("⬅ Back to Orders", callback_data="adm_ords"),
            InlineKeyboardButton("🏠 Admin Menu", callback_data="adm_main")
        ])

    return InlineKeyboardMarkup(buttons)

def admin_sync_panel_keyboard(is_running: bool, is_paused: bool) -> InlineKeyboardMarkup:
    buttons = []
    if not is_running:
        buttons.append([
            InlineKeyboardButton("🚀 Full Sync (Zero to Hero)", callback_data="adm_sync_full"),
            InlineKeyboardButton("▶ Quick Sync (Recent)", callback_data="adm_sync_start")
        ])
        buttons.append([
            InlineKeyboardButton("📥 Import JSON Export File", callback_data="adm_sync_upload_json"),
            InlineKeyboardButton("⚠️ Review Queue", callback_data="adm_prod_review_queue")
        ])
        buttons.append([
            InlineKeyboardButton("🔄 Retry Failed", callback_data="adm_sync_retry")
        ])
    else:
        if not is_paused:
            buttons.append([
                InlineKeyboardButton("⏸ Pause Sync", callback_data="adm_sync_pause"),
                InlineKeyboardButton("⛔ Cancel Sync", callback_data="adm_sync_cancel")
            ])
        else:
            buttons.append([
                InlineKeyboardButton("▶ Resume Sync", callback_data="adm_sync_resume"),
                InlineKeyboardButton("⛔ Cancel Sync", callback_data="adm_sync_cancel")
            ])

    buttons.append([
        InlineKeyboardButton("🔄 Refresh Progress", callback_data="adm_sync"),
        InlineKeyboardButton("🏠 Admin Menu", callback_data="adm_main")
    ])
    return InlineKeyboardMarkup(buttons)

def admin_settings_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🏪 Store Name & Info", callback_data="adm_set_info"), InlineKeyboardButton("🚚 Delivery Fee", callback_data="adm_set_fee")],
        [InlineKeyboardButton("💳 Payment Methods", callback_data="adm_set_payments"), InlineKeyboardButton("📞 Contact & Support", callback_data="adm_set_contact")],
        [InlineKeyboardButton("📢 Source Channel", callback_data="adm_set_channel"), InlineKeyboardButton("🏠 Admin Menu", callback_data="adm_main")]
    ])
