import re
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🛍 Shop All", callback_data="cust_shop"), InlineKeyboardButton("📂 Categories", callback_data="cust_categories")],
        [InlineKeyboardButton("🔥 New Arrivals", callback_data="cust_new"), InlineKeyboardButton("🏷 Offers", callback_data="cust_offers")],
        [InlineKeyboardButton("🔎 Search Products", callback_data="cust_search"), InlineKeyboardButton("🛒 My Cart", callback_data="cust_cart")],
        [InlineKeyboardButton("📦 My Orders", callback_data="cust_orders"), InlineKeyboardButton("📞 Contact Admin", callback_data="cust_contact")],
        [InlineKeyboardButton("ℹ️ Help & FAQ", callback_data="cust_help")]
    ])

def categories_keyboard(categories: list) -> InlineKeyboardMarkup:
    buttons = []
    # 2 per row
    row = []
    for cat in categories:
        icon = cat.get("icon") or "📁"
        name = cat["name"]
        slug = cat["slug"]
        row.append(InlineKeyboardButton(f"{icon} {name}", callback_data=f"cat_{slug}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton("⬅ Back to Menu", callback_data="cust_main")])
    return InlineKeyboardMarkup(buttons)

def format_product_display_name(p: dict) -> str:
    raw_name = p.get('name') or ''
    brand = (p.get('brand') or '').strip()
    condition = (p.get('condition') or '').strip()
    model = (p.get('model') or '').strip()
    description = (p.get('description') or '').strip()

    name = raw_name
    # Clean prefixes and promotional labels
    name = re.sub(r'^[🛍🔥🏷✨📱💻🖥🎉🛒\s]+', '', name).strip()
    name = re.sub(r'(?i)^(?:Weekly\s*Discount|Holiday\s*Discount|Special\s*Offer|Special|Offer#?|Budget\s*Phone\s*#?\s*\d*#?|Budget\s*iPhone\s*#?\s*\d*#?|Budget\s*Tab)\s*', '', name).strip()
    name = re.sub(r'^[🛍🔥🏷✨📱💻🖥\s\-#]+', '', name).strip()
    # Remove 'Brand New Packed' or 'Brand New' or 'Packed'
    name = re.sub(r'(?i)^(?:Brand\s*New\s*(?:Packed)?|Packed|Clean)\s*', '', name).strip()
    # Split on arrows or specs
    name = re.split(r'[\n\r➡️|]|\s+(?:\d+\s*GB\s+Storage|Storage|Battery|Price|Contact|Condition)\b', name, flags=re.IGNORECASE)[0].strip()
    name = re.sub(r'^[🛍🔥🏷✨📱💻🖥\s\-#]+|[🛍🔥🏷✨📱💻🖥\s\-#]+$', '', name).strip()

    # Determine New vs Used
    corpus = f"{raw_name} {condition} {description}".lower()
    is_new = bool(re.search(r'\b(?:brand\s*new|packed|አዲስ|ድንግል)\b', corpus) or (condition == 'Brand New'))
    
    # If the text explicitly indicates used
    if re.search(r'\b(?:slightly\s*used|used|የታደሰ|ያገለገለ)\b', corpus):
        is_new = False

    prefix = "New" if is_new else "Used"
    name = re.sub(r'^(?:New|Used)\s*', '', name, flags=re.IGNORECASE).strip()
    
    if not name:
        name = model or brand or 'Phone'
        
    return f"{prefix} {name}"

def products_list_keyboard(products: list, page: int, total_pages: int, category_slug: str = None) -> InlineKeyboardMarkup:
    buttons = []
    for p in products:
        title = format_product_display_name(p)
        if len(title) > 45:
            title = title[:42].strip() + "..."
        buttons.append([InlineKeyboardButton(title, callback_data=f"prod_view_{p['product_id']}")])

    # Pagination buttons
    nav_row = []
    cb_prefix = f"page_{category_slug or 'all'}"
    if page > 1:
        nav_row.append(InlineKeyboardButton("⬅ Prev", callback_data=f"{cb_prefix}_{page - 1}"))
    nav_row.append(InlineKeyboardButton(f"{page}/{max(1, total_pages)}", callback_data="noop"))
    if page < total_pages:
        nav_row.append(InlineKeyboardButton("Next ➡", callback_data=f"{cb_prefix}_{page + 1}"))

    if nav_row:
        buttons.append(nav_row)

    buttons.append([
        InlineKeyboardButton("🔎 Search", callback_data="cust_search"),
        InlineKeyboardButton("🛒 Cart", callback_data="cust_cart"),
        InlineKeyboardButton("🏠 Menu", callback_data="cust_main")
    ])
    return InlineKeyboardMarkup(buttons)

def product_detail_keyboard(product: dict, in_cart_qty: int = 0) -> InlineKeyboardMarkup:
    pid = product["product_id"]
    is_available = product.get("availability") == "Available"

    buttons = []
    if is_available:
        cart_txt = f"🛒 In Cart ({in_cart_qty}) +1" if in_cart_qty > 0 else "🛒 Add to Cart"
        buttons.append([
            InlineKeyboardButton(cart_txt, callback_data=f"cart_add_{pid}"),
            InlineKeyboardButton("⚡ Buy Now", callback_data=f"buy_now_{pid}")
        ])
    else:
        buttons.append([
            InlineKeyboardButton("❌ Currently Unavailable", callback_data="noop")
        ])

    buttons.append([
        InlineKeyboardButton("💬 Ask Admin", callback_data=f"ask_prod_{pid}"),
        InlineKeyboardButton("🛒 View Cart", callback_data="cust_cart")
    ])

    # Back navigation
    cat_slug = product.get("category_slug") or "all"
    buttons.append([
        InlineKeyboardButton("⬅ Back to Products", callback_data=f"cat_{cat_slug}"),
        InlineKeyboardButton("🏠 Main Menu", callback_data="cust_main")
    ])
    return InlineKeyboardMarkup(buttons)

def cart_keyboard(cart_items: list, subtotal: float, delivery_fee: float) -> InlineKeyboardMarkup:
    buttons = []
    if not cart_items:
        buttons.append([InlineKeyboardButton("🛍 Start Shopping", callback_data="cust_shop")])
        buttons.append([InlineKeyboardButton("⬅ Main Menu", callback_data="cust_main")])
        return InlineKeyboardMarkup(buttons)

    for item in cart_items:
        pid = item["product_id"]
        qty = item["quantity"]
        name = item["name"][:18]
        buttons.append([
            InlineKeyboardButton(f"{name}", callback_data=f"prod_view_{pid}"),
            InlineKeyboardButton("➖", callback_data=f"cart_dec_{pid}"),
            InlineKeyboardButton(f"{qty}", callback_data="noop"),
            InlineKeyboardButton("➕", callback_data=f"cart_inc_{pid}"),
            InlineKeyboardButton("🗑", callback_data=f"cart_rem_{pid}")
        ])

    buttons.append([
        InlineKeyboardButton("🗑 Clear", callback_data="cart_clear"),
        InlineKeyboardButton("🛍 Add More", callback_data="cust_shop")
    ])
    buttons.append([
        InlineKeyboardButton("🚀 Checkout", callback_data="cart_checkout")
    ])
    buttons.append([
        InlineKeyboardButton("⬅ Main Menu", callback_data="cust_main")
    ])
    return InlineKeyboardMarkup(buttons)

def payment_methods_keyboard(methods: list) -> InlineKeyboardMarkup:
    buttons = []
    for m in methods:
        m_id = m.get("id") or m.get("name")
        m_name = m.get("name")
        buttons.append([InlineKeyboardButton(f"💳 {m_name}", callback_data=f"pay_select_{m_id}")])
    buttons.append([InlineKeyboardButton("❌ Cancel", callback_data="cust_main")])
    return InlineKeyboardMarkup(buttons)

def order_detail_keyboard(order: dict) -> InlineKeyboardMarkup:
    oid = order["order_id"]
    status = order.get("order_status")
    pay_status = order.get("payment_status")

    buttons = []
    if pay_status in ["Pending", "Rejected"] and status not in ["Cancelled", "Delivered"]:
        buttons.append([InlineKeyboardButton("📤 Upload Receipt", callback_data=f"ord_upload_rcpt_{oid}")])

    buttons.append([
        InlineKeyboardButton("💬 Support", callback_data=f"cust_contact_ord_{oid}"),
        InlineKeyboardButton("📦 My Orders", callback_data="cust_orders")
    ])
    buttons.append([InlineKeyboardButton("🏠 Main Menu", callback_data="cust_main")])
    return InlineKeyboardMarkup(buttons)

def orders_list_keyboard(orders: list) -> InlineKeyboardMarkup:
    buttons = []
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
        icon = status_icons.get(o["order_status"], "📋")
        num = o["order_number"]
        tot = f"{o['total']:,.0f} ETB"
        buttons.append([InlineKeyboardButton(f"{icon} {num} ({tot})", callback_data=f"ord_view_{o['order_id']}")])

    buttons.append([InlineKeyboardButton("🛍 Shop More", callback_data="cust_shop")])
    buttons.append([InlineKeyboardButton("🏠 Main Menu", callback_data="cust_main")])
    return InlineKeyboardMarkup(buttons)
