import re
import uuid
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from admin_bot.handlers.auth import verify_admin_access
from admin_bot.keyboards import (
    admin_products_menu_keyboard, admin_products_list_keyboard,
    admin_product_detail_keyboard
)
from database.crud import (
    list_products, get_product_by_id, update_product,
    update_product_availability, update_product_price, update_product_stock,
    delete_product, create_product, get_all_categories, get_review_queue,
    add_product_image, get_product_images
)
from services.audit import log_admin_action
from services.ui_utils import safe_edit_or_send
from config import MEDIA_DIR

logger = logging.getLogger("iswitch.admin.products")

PAGE_SIZE = 8

async def products_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verify_admin_access(update, context):
        return

    text = "📦 *Product Management*\n\nSelect an action below to manage catalog items:"
    await safe_edit_or_send(update, context, text, reply_markup=admin_products_menu_keyboard())

async def list_products_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = None):
    if not await verify_admin_access(update, context):
        return

    query = update.callback_query
    # Extract page if not provided
    if page is None:
        if query and query.data:
            parts = query.data.split("_")
            page = int(parts[-1]) if parts[-1].isdigit() else 1
        else:
            page = 1

    offset = (page - 1) * PAGE_SIZE

    products, total = await list_products(offset=offset, limit=PAGE_SIZE, admin_view=True)
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)

    text = f"📦 *Product Catalog* (Page {page}/{total_pages} - Total: {total} items):\n\nTap any product to edit price, stock, status, or details:"
    kb = admin_products_list_keyboard(products, page, total_pages)
    await safe_edit_or_send(update, context, text, reply_markup=kb)

async def product_detail_admin(update: Update, context: ContextTypes.DEFAULT_TYPE, pid: int = None):
    if not await verify_admin_access(update, context):
        return

    query = update.callback_query
    if pid is None:
        if query and query.data:
            pid = int(query.data.replace("adm_pview_", ""))
        else:
            return

    prod = await get_product_by_id(pid)
    if not prod:
        if query:
            await query.answer("Product not found.", show_alert=True)
        return

    name = prod["name"]
    price = prod.get("price") or 0.0
    disc = prod.get("discount_price")
    stock = prod.get("stock_quantity", 0)
    avail = prod.get("availability", "Available")
    feat = "Yes ⭐" if prod.get("featured") else "No"
    arr = "Yes 🔥" if prod.get("new_arrival") else "No"
    cond = prod.get("condition", "N/A")
    storage = prod.get("storage", "N/A")
    color = prod.get("color", "N/A")
    cat_name = prod.get("category_name", "Uncategorized")
    src = prod.get("source_channel", "Manual Entry")
    src_msg = prod.get("source_message_id", "N/A")

    images = await get_product_images(pid)
    img_status = f"🖼 {len(images)} photo(s) attached" if images else "⚠️ No photo uploaded"

    lines = [
        f"📱 *PRODUCT ADMIN: #{pid}*\n",
        f"🏷 *Name:* *{name}*",
        f"📂 *Category:* {cat_name}",
        f"📸 *Images:* {img_status}",
        f"✨ *Condition:* {cond}",
        f"💾 *Storage:* {storage} | 🎨 *Color:* {color}",
        f"🔋 *Battery:* {prod.get('battery_health', 'N/A')}",
        f"💰 *Price:* {price:,.0f} ETB",
        f"🏷 *Discount Price:* {f'{disc:,.0f} ETB' if disc else 'None'}",
        f"📦 *Stock:* {stock} units ({avail})",
        f"⭐ *Featured:* {feat} | 🔥 *New Arrival:* {arr}",
        f"📡 *Source:* {src} (Post #{src_msg})\n",
        "Select an action to modify this product immediately in the database:"
    ]

    kb = admin_product_detail_keyboard(prod)
    await safe_edit_or_send(update, context, "\n".join(lines), reply_markup=kb)

async def toggle_availability(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verify_admin_access(update, context):
        return

    query = update.callback_query
    admin_id = update.effective_user.id

    if "adm_ptog_sold_" in query.data:
        pid = int(query.data.replace("adm_ptog_sold_", ""))
        new_avail = "Sold"
    else:
        pid = int(query.data.replace("adm_ptog_avail_", ""))
        new_avail = "Available"

    prod = await get_product_by_id(pid)
    old_avail = prod.get("availability")
    await update_product_availability(pid, new_avail)
    await log_admin_action(admin_id, "update_product_availability", "product", pid, old_avail, new_avail)

    await query.answer(f"Availability changed to {new_avail}!")
    await product_detail_admin(update, context, pid=pid)

async def toggle_featured(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verify_admin_access(update, context):
        return

    query = update.callback_query
    pid = int(query.data.replace("adm_ptog_feat_", ""))
    prod = await get_product_by_id(pid)
    new_feat = 0 if prod.get("featured") else 1

    await update_product(pid, featured=new_feat)
    await log_admin_action(update.effective_user.id, "toggle_featured", "product", pid, str(prod.get("featured")), str(new_feat))

    await query.answer(f"Featured status: {'ON ⭐' if new_feat else 'OFF'}")
    await product_detail_admin(update, context, pid=pid)

async def toggle_new_arrival(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verify_admin_access(update, context):
        return

    query = update.callback_query
    pid = int(query.data.replace("adm_ptog_arr_", ""))
    prod = await get_product_by_id(pid)
    new_arr = 0 if prod.get("new_arrival") else 1

    await update_product(pid, new_arrival=new_arr)
    await log_admin_action(update.effective_user.id, "toggle_new_arrival", "product", pid, str(prod.get("new_arrival")), str(new_arr))

    await query.answer(f"New Arrival: {'ON 🔥' if new_arr else 'OFF'}")
    await product_detail_admin(update, context, pid=pid)

async def prompt_edit_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verify_admin_access(update, context):
        return

    query = update.callback_query
    pid = int(query.data.replace("adm_pedt_price_", ""))
    context.user_data["editing_product_price"] = pid

    kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅ Cancel", callback_data=f"adm_pview_{pid}")]])
    msg = f"💰 *Edit Price for Product #{pid}*\n\nPlease reply with the new price in ETB (e.g., `24500`):"
    await safe_edit_or_send(update, context, msg, reply_markup=kb)

async def handle_price_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    pid = context.user_data.get("editing_product_price")
    if not pid:
        return False

    text = update.message.text.strip().replace(",", "")
    try:
        new_price = float(text)
        if new_price <= 0 or new_price > 100_000_000:
            await update.message.reply_text("❌ Price must be a positive number greater than 0.")
            return True
    except ValueError:
        await update.message.reply_text("Please enter a valid numeric price (e.g., `25000`):")
        return True

    context.user_data["editing_product_price"] = None
    prod = await get_product_by_id(pid)
    old_price = str(prod.get("price"))
    await update_product_price(pid, new_price)
    await log_admin_action(update.effective_user.id, "price_changed", "product", pid, old_price, str(new_price))

    kb = InlineKeyboardMarkup([[InlineKeyboardButton("👁 View Product", callback_data=f"adm_pview_{pid}")]])
    await update.message.reply_text(
        f"✅ Price updated to *{new_price:,.2f} ETB* for *{prod['name']}*!",
        parse_mode="Markdown",
        reply_markup=kb
    )
    return True

async def prompt_edit_discount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verify_admin_access(update, context):
        return

    query = update.callback_query
    pid = int(query.data.replace("adm_pedt_disc_", ""))
    context.user_data["editing_product_discount"] = pid

    kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅ Cancel", callback_data=f"adm_pview_{pid}")]])
    msg = f"🏷 *Set Discount Price for Product #{pid}*\n\nPlease reply with the discounted sale price in ETB (or type `0` to remove discount):"
    await safe_edit_or_send(update, context, msg, reply_markup=kb)

async def handle_discount_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    pid = context.user_data.get("editing_product_discount")
    if not pid:
        return False

    text = update.message.text.strip().replace(",", "")
    try:
        disc_val = float(text)
        if disc_val < 0 or disc_val > 100_000_000:
            await update.message.reply_text("❌ Discount price must be 0 or a positive number.")
            return True
    except ValueError:
        await update.message.reply_text("Please enter a valid numeric price or 0 to clear:")
        return True

    context.user_data["editing_product_discount"] = None
    new_disc = disc_val if disc_val > 0 else None
    await update_product(pid, discount_price=new_disc)
    await log_admin_action(update.effective_user.id, "discount_updated", "product", pid, details=str(new_disc))

    kb = InlineKeyboardMarkup([[InlineKeyboardButton("👁 View Product", callback_data=f"adm_pview_{pid}")]])
    status_txt = f"Discount set to *{disc_val:,.2f} ETB*" if disc_val > 0 else "Discount removed."
    await update.message.reply_text(f"✅ {status_txt}", parse_mode="Markdown", reply_markup=kb)
    return True

async def prompt_edit_stock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verify_admin_access(update, context):
        return

    query = update.callback_query
    pid = int(query.data.replace("adm_pedt_stock_", ""))
    context.user_data["editing_product_stock"] = pid

    kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅ Cancel", callback_data=f"adm_pview_{pid}")]])
    msg = f"📦 *Edit Stock for Product #{pid}*\n\nPlease reply with the new stock quantity (e.g., `5`):"
    await safe_edit_or_send(update, context, msg, reply_markup=kb)

async def handle_stock_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    pid = context.user_data.get("editing_product_stock")
    if not pid:
        return False

    text = update.message.text.strip()
    try:
        new_stock = int(text)
        if new_stock < 0 or new_stock > 1_000_000:
            await update.message.reply_text("❌ Stock quantity must be a non-negative whole number (0 or higher).")
            return True
    except ValueError:
        await update.message.reply_text("Please enter a valid whole number for stock quantity:")
        return True

    context.user_data["editing_product_stock"] = None
    await update_product_stock(pid, new_stock)
    await log_admin_action(update.effective_user.id, "stock_changed", "product", pid, details=str(new_stock))

    kb = InlineKeyboardMarkup([[InlineKeyboardButton("👁 View Product", callback_data=f"adm_pview_{pid}")]])
    await update.message.reply_text(f"✅ Stock updated to *{new_stock}* units!", parse_mode="Markdown", reply_markup=kb)
    return True

async def prompt_edit_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verify_admin_access(update, context):
        return

    query = update.callback_query
    pid = int(query.data.replace("adm_pedt_cat_", ""))
    cats = await get_all_categories(active_only=False)

    buttons = []
    for c in cats:
        buttons.append([InlineKeyboardButton(f"{c.get('icon', '📁')} {c['name']}", callback_data=f"adm_pcat_set_{pid}_{c['category_id']}")])
    buttons.append([InlineKeyboardButton("⬅ Cancel", callback_data=f"adm_pview_{pid}")])

    msg = f"📁 *Select Category for Product #{pid}:*"
    await safe_edit_or_send(update, context, msg, reply_markup=InlineKeyboardMarkup(buttons))

async def set_product_category_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verify_admin_access(update, context):
        return

    query = update.callback_query
    # adm_pcat_set_{pid}_{cid}
    parts = query.data.split("_")
    pid = int(parts[3])
    cid = int(parts[4])

    await update_product(pid, category_id=cid)
    await log_admin_action(update.effective_user.id, "category_changed", "product", pid, details=f"New category: {cid}")
    await query.answer("Category updated!")
    await product_detail_admin(update, context, pid=pid)

async def prompt_product_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verify_admin_access(update, context):
        return

    context.user_data["awaiting_admin_prod_search"] = True
    msg = (
        "🔎 *Search Products in Catalog*\n\n"
        "Please reply with a product name, brand, or model to search:\n"
        "_(e.g., iPhone 15, Samsung, AirPods, Series 9)_"
    )
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅ Cancel", callback_data="adm_prods")]])
    await safe_edit_or_send(update, context, msg, reply_markup=kb)

async def handle_product_search_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if not context.user_data.get("awaiting_admin_prod_search"):
        return False

    context.user_data["awaiting_admin_prod_search"] = False
    term = update.message.text.strip()
    products, total = await list_products(search=term, limit=15, offset=0, admin_view=True)

    if not products:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔎 Search Again", callback_data="adm_prod_search")],
            [InlineKeyboardButton("📦 Products Menu", callback_data="adm_prods")]
        ])
        await update.message.reply_text(f"🔎 No products found matching '*{term}*'.", parse_mode="Markdown", reply_markup=kb)
        return True

    text = f"🔎 *Search Results for:* '_{term}_' ({len(products)} found):\n\nTap a product to edit:"
    kb = admin_products_list_keyboard(products, 1, 1)
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)
    return True

async def get_category_selection_keyboard(prefix: str = "adm_addp_cat_") -> InlineKeyboardMarkup:
    cats = await get_all_categories()
    buttons = []
    row = []
    for c in cats:
        icon = c.get("icon", "📦")
        name = c["name"]
        cid = c["category_id"]
        row.append(InlineKeyboardButton(f"{icon} {name}", callback_data=f"{prefix}{cid}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([
        InlineKeyboardButton("⏭ Skip Category", callback_data=f"{prefix}skip"),
        InlineKeyboardButton("⬅ Cancel", callback_data="adm_addp_cancel")
    ])
    return InlineKeyboardMarkup(buttons)

def get_condition_selection_keyboard(prefix: str = "adm_addp_cond_") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🆕 Brand New (Sealed)", callback_data=f"{prefix}Brand New")],
        [InlineKeyboardButton("✨ Slightly Used (Like New)", callback_data=f"{prefix}Slightly Used")],
        [InlineKeyboardButton("📱 Used (Good Condition)", callback_data=f"{prefix}Used")],
        [InlineKeyboardButton("🔄 Refurbished", callback_data=f"{prefix}Refurbished")],
        [InlineKeyboardButton("⏭ Skip Condition", callback_data=f"{prefix}skip")],
        [InlineKeyboardButton("⬅ Cancel", callback_data="adm_addp_cancel")]
    ])

def get_quantity_selection_keyboard(prefix: str = "adm_addp_qty_") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("1 unit", callback_data=f"{prefix}1"),
            InlineKeyboardButton("2 units", callback_data=f"{prefix}2"),
            InlineKeyboardButton("3 units", callback_data=f"{prefix}3")
        ],
        [
            InlineKeyboardButton("5 units", callback_data=f"{prefix}5"),
            InlineKeyboardButton("10 units", callback_data=f"{prefix}10"),
            InlineKeyboardButton("20 units", callback_data=f"{prefix}20")
        ],
        [
            InlineKeyboardButton("50 units", callback_data=f"{prefix}50"),
            InlineKeyboardButton("100 units", callback_data=f"{prefix}100")
        ],
        [InlineKeyboardButton("⬅ Cancel", callback_data="adm_addp_cancel")]
    ])

def get_storage_selection_keyboard(prefix: str = "adm_addp_stor_") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("64GB", callback_data=f"{prefix}64GB"),
            InlineKeyboardButton("128GB", callback_data=f"{prefix}128GB"),
            InlineKeyboardButton("256GB", callback_data=f"{prefix}256GB")
        ],
        [
            InlineKeyboardButton("512GB", callback_data=f"{prefix}512GB"),
            InlineKeyboardButton("1TB", callback_data=f"{prefix}1TB"),
            InlineKeyboardButton("2TB", callback_data=f"{prefix}2TB")
        ],
        [InlineKeyboardButton("⏭ Skip Specs / None", callback_data="adm_addp_desc_skip")],
        [InlineKeyboardButton("⬅ Cancel", callback_data="adm_addp_cancel")]
    ])

def parse_product_specs_text(text: str) -> dict:
    specs = {}
    if not text:
        return specs
    # Storage
    stor = re.search(r'\b(64|128|256|512)\s*GB\b|\b(1|2)\s*TB\b', text, re.IGNORECASE)
    if stor:
        specs["storage"] = stor.group(0).upper().replace(" ", "")
    # RAM
    ram = re.search(r'\b(4|6|8|12|16|18|24|32|36|64|128)\s*GB\s*RAM\b', text, re.IGNORECASE)
    if ram:
        specs["ram"] = ram.group(0).upper()
    # Battery health
    bat = re.search(r'\b(100|[89]\d)%(?:\s*battery)?', text, re.IGNORECASE)
    if bat:
        specs["battery_health"] = f"{bat.group(1)}%"
    # Common colors
    colors = [
        "Natural Titanium", "Desert Titanium", "Black Titanium", "White Titanium", "Blue Titanium",
        "Space Black", "Space Gray", "Midnight", "Starlight", "Silver", "Gold", "Rose Gold",
        "Deep Purple", "Graphite", "Alpine Green", "Sierra Blue", "Pacific Blue",
        "Black", "White", "Blue", "Green", "Yellow", "Pink", "Red", "Purple"
    ]
    for c in colors:
        if re.search(rf'\b{re.escape(c)}\b', text, re.IGNORECASE):
            specs["color"] = c
            break
    return specs

async def prompt_add_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verify_admin_access(update, context):
        return

    context.user_data["add_product_step"] = "name"
    context.user_data["new_product"] = {}

    msg = (
        "➕ *Add New Product (Step 1/6)*\n\n"
        "Please reply with the *Product Name*:\n"
        "_(e.g., iPhone 15 Pro Max, Samsung S24 Ultra, MacBook Pro M3, AirPods Pro 2)_"
    )
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅ Cancel", callback_data="adm_addp_cancel")]])
    await safe_edit_or_send(update, context, msg, reply_markup=kb)

async def set_add_product_category_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verify_admin_access(update, context):
        return

    query = update.callback_query
    await query.answer()

    cat_val = query.data.replace("adm_addp_cat_", "")
    new_prod = context.user_data.get("new_product", {})
    cat_name = "Uncategorized"

    if cat_val != "skip" and cat_val.isdigit():
        new_prod["category_id"] = int(cat_val)
        cats = await get_all_categories()
        for c in cats:
            if c["category_id"] == int(cat_val):
                cat_name = f"{c.get('icon', '')} {c['name']}".strip()
                break
    else:
        new_prod["category_id"] = None

    new_prod["category_name"] = cat_name
    context.user_data["new_product"] = new_prod
    context.user_data["add_product_step"] = "condition"
    name = new_prod.get("name", "Product")

    msg = (
        f"➕ *Add New Product (Step 3/6)*\n\n"
        f"📦 *Product:* *{name}*\n"
        f"📁 *Category:* {cat_name}\n\n"
        "Select the *Condition* of the product:"
    )
    kb = get_condition_selection_keyboard()
    await safe_edit_or_send(update, context, msg, reply_markup=kb)

async def set_add_product_condition_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verify_admin_access(update, context):
        return

    query = update.callback_query
    await query.answer()

    cond_val = query.data.replace("adm_addp_cond_", "")
    new_prod = context.user_data.get("new_product", {})
    condition = None if cond_val == "skip" else cond_val
    new_prod["condition"] = condition
    context.user_data["new_product"] = new_prod
    context.user_data["add_product_step"] = "qty"

    name = new_prod.get("name", "Product")
    cond_display = condition or "Not Specified"

    msg = (
        f"➕ *Add New Product (Step 4/6)*\n\n"
        f"📦 *Product:* *{name}*\n"
        f"✨ *Condition:* {cond_display}\n\n"
        "Select or type the *Available Quantity (Stock)*:\n"
        "_(Tap a button below or type any exact number in chat)_"
    )
    kb = get_quantity_selection_keyboard()
    await safe_edit_or_send(update, context, msg, reply_markup=kb)

async def set_add_product_qty_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verify_admin_access(update, context):
        return

    query = update.callback_query
    await query.answer()

    qty_str = query.data.replace("adm_addp_qty_", "")
    qty = int(qty_str) if qty_str.isdigit() else 1
    new_prod = context.user_data.get("new_product", {})
    new_prod["stock_quantity"] = qty
    context.user_data["new_product"] = new_prod
    context.user_data["add_product_step"] = "price"

    name = new_prod.get("name", "Product")
    cond_display = new_prod.get("condition") or "Brand New"

    msg = (
        f"➕ *Add New Product (Step 5/6)*\n\n"
        f"📦 *Product:* *{name}*\n"
        f"✨ *Condition:* {cond_display}\n"
        f"🔢 *Quantity:* {qty} unit(s) in stock\n\n"
        "Please reply with the *Price in ETB*:\n"
        "_(e.g., 120000 or 85,500)_"
    )
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅ Cancel", callback_data="adm_addp_cancel")]])
    await safe_edit_or_send(update, context, msg, reply_markup=kb)

async def set_add_product_storage_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verify_admin_access(update, context):
        return

    query = update.callback_query
    await query.answer()

    stor = query.data.replace("adm_addp_stor_", "")
    await finalize_product_creation(update, context, desc=f"{stor} Storage", storage=stor)

async def skip_add_product_desc_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verify_admin_access(update, context):
        return
    query = update.callback_query
    await query.answer()
    await finalize_product_creation(update, context, desc="")

async def cancel_add_product_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verify_admin_access(update, context):
        return
    query = update.callback_query
    await query.answer("Product creation cancelled.")
    context.user_data.pop("add_product_step", None)
    context.user_data.pop("new_product", None)
    context.user_data.pop("awaiting_product_photo_id", None)
    await products_menu(update, context)

async def skip_add_product_photo_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verify_admin_access(update, context):
        return
    query = update.callback_query
    await query.answer("Product saved without photo.")
    pid = int(query.data.replace("adm_addp_photo_skip_", ""))
    context.user_data.pop("awaiting_product_photo_id", None)

    prod = await get_product_by_id(pid)
    name = prod.get("name", f"Product #{pid}")
    msg = (
        f"✅ *Product #{pid} is Published!*\n\n"
        f"📦 *Name:* *{name}*\n"
        "💡 You can add or update its photo anytime by tapping *📸 Add / Change Photo* in the product screen."
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("👁 View Product Card", callback_data=f"adm_pview_{pid}")],
        [InlineKeyboardButton("➕ Add Another Product", callback_data="adm_prod_add")],
        [InlineKeyboardButton("📦 All Products", callback_data="adm_prod_list_1")]
    ])
    await safe_edit_or_send(update, context, msg, reply_markup=kb)

async def finalize_product_creation(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    desc: str = "",
    storage: str = None
):
    new_prod = context.user_data.get("new_product", {})
    name = new_prod.get("name", "Untitled Product")
    price = new_prod.get("price", 0.0)
    cat_id = new_prod.get("category_id")
    condition = new_prod.get("condition") or "Brand New"
    stock_qty = new_prod.get("stock_quantity", 1)

    parsed_specs = parse_product_specs_text(desc) if desc else {}
    if storage:
        parsed_specs["storage"] = storage
    elif not parsed_specs.get("storage") and new_prod.get("storage"):
        parsed_specs["storage"] = new_prod.get("storage")

    pid = await create_product(
        name=name,
        category_id=cat_id,
        price=price,
        description=desc,
        condition=condition,
        stock_quantity=stock_qty,
        storage=parsed_specs.get("storage"),
        ram=parsed_specs.get("ram"),
        color=parsed_specs.get("color"),
        battery_health=parsed_specs.get("battery_health"),
        availability="Available" if stock_qty > 0 else "Out of Stock",
        approval_status="Published"
    )
    admin_id = update.effective_user.id if update.effective_user else 0
    await log_admin_action(admin_id, "product_created_manually", "product", pid, None, name)

    context.user_data["awaiting_product_photo_id"] = pid
    context.user_data.pop("add_product_step", None)
    context.user_data.pop("new_product", None)

    msg = (
        f"🎉 *Product Created Successfully!* (#ISW-{pid})\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 *Name:* *{name}*\n"
        f"💰 *Price:* *{price:,.0f} ETB*\n"
        f"✨ *Condition:* {condition}\n"
        f"🔢 *Stock:* {stock_qty} unit(s) (Available)\n"
    )
    if parsed_specs.get("storage"):
        msg += f"💾 *Storage:* {parsed_specs['storage']}\n"
    if parsed_specs.get("color"):
        msg += f"🎨 *Color:* {parsed_specs['color']}\n"
    if parsed_specs.get("battery_health"):
        msg += f"🔋 *Battery:* {parsed_specs['battery_health']}\n"
    if desc:
        msg += f"📝 *Details:* {desc}\n"
    msg += (
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        "📸 *Now please send the Product Image:*\n"
        "Simply send a photo from your phone/gallery to attach it to this product!\n\n"
        "_(Or tap Skip if you don't have a photo right now)_"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("⏭ Skip Photo / Finish", callback_data=f"adm_addp_photo_skip_{pid}")],
        [InlineKeyboardButton("👁 View Product Card", callback_data=f"adm_pview_{pid}")]
    ])
    if update.callback_query:
        await safe_edit_or_send(update, context, msg, reply_markup=kb)
    elif update.message:
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=kb)

async def prompt_edit_condition(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verify_admin_access(update, context):
        return

    query = update.callback_query
    pid = int(query.data.replace("adm_pedt_cond_", ""))
    prod = await get_product_by_id(pid)
    name = prod.get("name", f"Product #{pid}")
    current_cond = prod.get("condition", "N/A")

    msg = (
        f"✨ *Change Condition for Product #{pid}*\n"
        f"📦 *{name}*\n"
        f"Current: *{current_cond}*\n\n"
        f"Select the new condition:"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🆕 Brand New (Sealed)", callback_data=f"adm_pcond_set_{pid}_Brand New")],
        [InlineKeyboardButton("✨ Slightly Used (Like New)", callback_data=f"adm_pcond_set_{pid}_Slightly Used")],
        [InlineKeyboardButton("📱 Used (Good Condition)", callback_data=f"adm_pcond_set_{pid}_Used")],
        [InlineKeyboardButton("🔄 Refurbished", callback_data=f"adm_pcond_set_{pid}_Refurbished")],
        [InlineKeyboardButton("⬅ Cancel", callback_data=f"adm_pview_{pid}")]
    ])
    await safe_edit_or_send(update, context, msg, reply_markup=kb)

async def set_product_condition_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verify_admin_access(update, context):
        return

    query = update.callback_query
    data = query.data.replace("adm_pcond_set_", "")
    parts = data.split("_", 1)
    pid = int(parts[0])
    new_cond = parts[1]

    await update_product(pid, condition=new_cond)
    admin_id = update.effective_user.id if update.effective_user else 0
    await log_admin_action(admin_id, "product_condition_updated", "product", pid, None, new_cond)
    await query.answer(f"Condition updated to {new_cond}!")
    await product_detail_admin(update, context, pid=pid)

async def handle_add_product_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    step = context.user_data.get("add_product_step")
    if not step:
        return False

    text = update.message.text.strip()

    if step == "name":
        context.user_data.setdefault("new_product", {})["name"] = text
        context.user_data["add_product_step"] = "category"

        msg = (
            f"➕ *Add New Product (Step 2/6)*\n\n"
            f"📦 *Product Name:* *{text}*\n\n"
            "Select a *Category* below:"
        )
        kb = await get_category_selection_keyboard(prefix="adm_addp_cat_")
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=kb)
        return True

    elif step == "qty":
        clean_text = text.replace(",", "").strip()
        try:
            qty = int(clean_text)
            if qty < 0:
                raise ValueError()
        except ValueError:
            await update.message.reply_text("❌ Please enter a valid quantity number (e.g., `1`, `5`, `10`):", parse_mode="Markdown")
            return True

        context.user_data.setdefault("new_product", {})["stock_quantity"] = qty
        context.user_data["add_product_step"] = "price"
        new_prod = context.user_data["new_product"]
        name = new_prod.get("name", "Product")
        cond_display = new_prod.get("condition") or "Brand New"

        msg = (
            f"➕ *Add New Product (Step 5/6)*\n\n"
            f"📦 *Product:* *{name}*\n"
            f"✨ *Condition:* {cond_display}\n"
            f"🔢 *Quantity:* {qty} unit(s) in stock\n\n"
            "Please reply with the *Price in ETB*:\n"
            "_(e.g., 120000 or 85,500)_"
        )
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅ Cancel", callback_data="adm_addp_cancel")]])
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=kb)
        return True

    elif step == "price":
        clean_text = text.replace(",", "").replace("ETB", "").replace("etb", "").replace("birr", "").replace("Birr", "").strip()
        try:
            price = float(clean_text)
            if price <= 0:
                raise ValueError()
        except ValueError:
            await update.message.reply_text("❌ Please enter a valid positive number for price (e.g., `120000` or `85500`):", parse_mode="Markdown")
            return True

        context.user_data.setdefault("new_product", {})["price"] = price
        context.user_data["add_product_step"] = "desc"
        new_prod = context.user_data["new_product"]
        name = new_prod.get("name", "Product")
        cond_display = new_prod.get("condition") or "Brand New"
        qty = new_prod.get("stock_quantity", 1)

        msg = (
            f"➕ *Add New Product (Step 6/6)*\n\n"
            f"📦 *Product:* *{name}*\n"
            f"💰 *Price:* *{price:,.0f} ETB*\n"
            f"✨ *Condition:* {cond_display}\n"
            f"🔢 *Quantity:* {qty} unit(s)\n\n"
            "Please reply with *Specifications & Details*:\n"
            "_(e.g., 256GB Storage, Natural Titanium, 100% Battery, 1 Year Warranty)_\n\n"
            "Or select a *Quick Storage* button below:"
        )
        kb = get_storage_selection_keyboard()
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=kb)
        return True

    elif step == "desc":
        await finalize_product_creation(update, context, desc=text)
        return True

    return False

async def prompt_edit_product_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verify_admin_access(update, context):
        return

    query = update.callback_query
    pid = int(query.data.replace("adm_pedt_photo_", ""))
    context.user_data["awaiting_product_photo_id"] = pid

    prod = await get_product_by_id(pid)
    name = prod.get("name", f"Product #{pid}")

    msg = (
        f"📸 *Upload Photo for Product #{pid}*\n"
        f"📦 *{name}*\n\n"
        "Please send the product image now from your camera or gallery:"
    )
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅ Cancel", callback_data=f"adm_pview_{pid}")]])
    await safe_edit_or_send(update, context, msg, reply_markup=kb)

async def handle_admin_photo_upload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if not await verify_admin_access(update, context):
        return False

    pid = context.user_data.get("awaiting_product_photo_id")
    if not pid:
        return False

    context.user_data.pop("awaiting_product_photo_id", None)
    photo = update.message.photo[-1]

    try:
        tg_file = await context.bot.get_file(photo.file_id)
        filename = f"prod_{pid}_{uuid.uuid4().hex[:8]}.jpg"
        file_path = MEDIA_DIR / filename
        await tg_file.download_to_drive(file_path)

        await add_product_image(
            product_id=pid,
            file_path=str(file_path),
            is_primary=1,
            telegram_file_id=photo.file_id
        )

        prod = await get_product_by_id(pid)
        name = prod.get("name", f"Product #{pid}")
        price = prod.get("price", 0.0)

        caption = (
            f"🎉 *Product Photo Uploaded & Saved!* 📸\n\n"
            f"📦 *Product:* *{name}*\n"
            f"💰 *Price:* *{price:,.0f} ETB*\n"
            f"🟢 *Status:* Published in Store Catalog\n\n"
            f"Customers can now see this photo when browsing the Customer Bot!"
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("👁 View in Catalog", callback_data=f"adm_pview_{pid}")],
            [InlineKeyboardButton("➕ Add Another Product", callback_data="adm_prod_add")],
            [InlineKeyboardButton("📦 All Products", callback_data="adm_prod_list_1")]
        ])
        await update.message.reply_photo(
            photo=photo.file_id,
            caption=caption,
            parse_mode="Markdown",
            reply_markup=kb
        )
        return True
    except Exception as e:
        logger.error(f"Failed to save uploaded product photo: {e}", exc_info=True)
        await update.message.reply_text(
            f"⚠️ Photo upload error: {e}. Tap below to try again:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅ Back to Product", callback_data=f"adm_pview_{pid}")]])
        )
        return True

async def delete_product_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verify_admin_access(update, context):
        return

    query = update.callback_query
    pid = int(query.data.replace("adm_pdel_confirm_", ""))

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🗑 Yes, Delete Permanently", callback_data=f"adm_pdel_exec_{pid}")],
        [InlineKeyboardButton("⬅ Cancel", callback_data=f"adm_pview_{pid}")]
    ])
    msg = f"⚠️ *Confirm Delete Product #{pid}*\n\nAre you sure you want to delete this product from the database?"
    await safe_edit_or_send(update, context, msg, reply_markup=kb)

async def delete_product_execute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verify_admin_access(update, context):
        return

    query = update.callback_query
    pid = int(query.data.replace("adm_pdel_exec_", ""))

    prod = await get_product_by_id(pid)
    name = prod["name"] if prod else f"#{pid}"
    await delete_product(pid)
    await log_admin_action(update.effective_user.id, "product_deleted", "product", pid, name, "DELETED")

    await query.answer("Product deleted successfully!")
    await list_products_handler(update, context, page=1)

async def review_queue_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verify_admin_access(update, context):
        return

    rows, total = await get_review_queue(limit=10)
    if not rows:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📦 Products", callback_data="adm_prods")],
            [InlineKeyboardButton("🏠 Admin Menu", callback_data="adm_main")]
        ])
        msg = "✅ *Review Queue is Empty*\n\nAll imported channel products have been successfully parsed and published!"
        await safe_edit_or_send(update, context, msg, reply_markup=kb)
        return

    text = f"⚠️ *Product Review Queue ({total} items)*\n\nThese posts appeared to be products but lacked complete price or details:\n\n"
    buttons = []
    for r in rows:
        mid = r["message_id"]
        snippet = (r.get("message_text") or "")[:35].replace("\n", " ")
        buttons.append([InlineKeyboardButton(f"Post #{mid}: {snippet}...", callback_data=f"adm_rev_msg_{mid}")])

    buttons.append([InlineKeyboardButton("⬅ Products Menu", callback_data="adm_prods")])
    await safe_edit_or_send(update, context, text, reply_markup=InlineKeyboardMarkup(buttons))

async def review_queue_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verify_admin_access(update, context):
        return

    query = update.callback_query
    mid = int(query.data.replace("adm_rev_msg_", ""))
    from database.db import db
    row = await db.fetch_one("SELECT * FROM channel_messages WHERE message_id = ?;", (mid,))
    if not row:
        await query.answer("Message not found.", show_alert=True)
        return

    msg_txt = row.get("message_text") or "No text"
    status = row.get("processing_status", "Needs Review")

    text = (
        f"⚠️ *Review Queue Item: Post #{mid}*\n\n"
        f"Status: `{status}`\n\n"
        f"━━━━━━━━ Content ━━━━━━━━\n"
        f"{msg_txt[:800]}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅ Back to Review Queue", callback_data="adm_prod_review_queue")],
        [InlineKeyboardButton("📦 Products Menu", callback_data="adm_prods")]
    ])
    await safe_edit_or_send(update, context, text, reply_markup=kb)
