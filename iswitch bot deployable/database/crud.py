import json
import logging
from pathlib import Path
from datetime import datetime
from database.db import db
from database.models import DEFAULT_CATEGORIES, DEFAULT_SETTINGS
from config import ADMIN_USER_IDS, TELEGRAM_CHANNEL

logger = logging.getLogger("iswitch.crud")

# ========================================================
# SEEDING & INITIALIZATION
# ========================================================

async def seed_initial_data():
    """Seeds default categories, settings, and authorized admins."""
    # Seed Categories
    existing_cats = await db.fetch_all("SELECT slug FROM categories;")
    existing_slugs = {c["slug"] for c in existing_cats}
    for cat in DEFAULT_CATEGORIES:
        if cat["slug"] not in existing_slugs:
            await db.execute(
                """INSERT INTO categories (name, slug, icon, description, display_order, is_active)
                   VALUES (?, ?, ?, ?, ?, 1);""",
                (cat["name"], cat["slug"], cat["icon"], cat["description"], cat["display_order"])
            )

    # Seed System Settings
    for key, val in DEFAULT_SETTINGS.items():
        existing_val = await db.fetch_one("SELECT value FROM system_settings WHERE key = ?;", (key,))
        if not existing_val:
            await db.execute(
                "INSERT INTO system_settings (key, value, description) VALUES (?, ?, ?);",
                (key, val, f"Initial default setting for {key}")
            )

    # Seed Admins
    for admin_id in ADMIN_USER_IDS:
        admin = await db.fetch_one("SELECT id FROM admins WHERE telegram_id = ?;", (admin_id,))
        if not admin:
            await db.execute(
                "INSERT INTO admins (telegram_id, role, is_active) VALUES (?, 'superadmin', 1);",
                (admin_id,)
            )

    # Seed Channel Source
    channel_src = await db.fetch_one("SELECT source_id FROM channel_sources WHERE channel_username = ?;", (TELEGRAM_CHANNEL,))
    if not channel_src:
        await db.execute(
            "INSERT INTO channel_sources (channel_username, channel_title, is_active) VALUES (?, 'iSwitch Official', 1);",
            (TELEGRAM_CHANNEL,)
        )

    # Auto-seed initial catalog products if table is empty
    prod_cnt_row = await db.fetch_one("SELECT COUNT(*) as cnt FROM products;")
    if prod_cnt_row and prod_cnt_row["cnt"] == 0:
        seed_file = Path(__file__).resolve().parent / "seed_products.json"
        if seed_file.exists():
            try:
                with open(seed_file, "r", encoding="utf-8") as f:
                    seed_prods = json.load(f)

                cats = await db.fetch_all("SELECT category_id, slug FROM categories;")
                slug_to_id = {c["slug"]: c["category_id"] for c in cats}

                logger.info(f"Auto-seeding {len(seed_prods)} catalog products from {seed_file.name}...")
                for p in seed_prods:
                    cat_id = slug_to_id.get(p.get("category_slug")) or p.get("category_id") or 1
                    pid = await db.execute(
                        """INSERT INTO products (
                            name, category_id, brand, model, description, price, currency,
                            condition, storage, ram, color, battery_health, stock_quantity,
                            availability, approval_status, featured, new_arrival, discount_price,
                            discount_percentage, source_channel, source_channel_id, source_message_id,
                            source_message_url, source_message_date, parse_confidence
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);""",
                        (
                            p.get("name"), cat_id, p.get("brand"), p.get("model"),
                            p.get("description"), p.get("price"), p.get("currency", "ETB"),
                            p.get("condition"), p.get("storage"), p.get("ram"), p.get("color"),
                            p.get("battery_health"), p.get("stock_quantity", 1),
                            p.get("availability", "Available"), p.get("approval_status", "Published"),
                            p.get("featured", 0), p.get("new_arrival", 0), p.get("discount_price"),
                            p.get("discount_percentage"), p.get("source_channel"), p.get("source_channel_id"),
                            p.get("source_message_id"), p.get("source_message_url"),
                            p.get("source_message_date"), p.get("parse_confidence", 1.0)
                        )
                    )
                    for img in p.get("images", []):
                        await db.execute(
                            """INSERT INTO product_images (product_id, file_path, file_url, telegram_file_id, is_primary)
                               VALUES (?, ?, ?, ?, ?);""",
                            (pid, img.get("file_path", ""), img.get("file_url"), img.get("telegram_file_id"), img.get("is_primary", 0))
                        )
                logger.info(f"Successfully auto-seeded {len(seed_prods)} products into catalog.")
            except Exception as se_err:
                logger.warning(f"Auto-seeding products encountered error: {se_err}")

# ========================================================
# ADMIN OPERATIONS
# ========================================================

async def is_admin(telegram_id: int) -> bool:
    if telegram_id in ADMIN_USER_IDS:
        return True
    row = await db.fetch_one("SELECT id FROM admins WHERE telegram_id = ? AND is_active = 1;", (telegram_id,))
    return bool(row)

async def get_admin(telegram_id: int) -> dict | None:
    return await db.fetch_one("SELECT * FROM admins WHERE telegram_id = ?;", (telegram_id,))

async def update_admin_last_seen(telegram_id: int, username: str = None, first_name: str = None):
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    await db.execute(
        """INSERT INTO admins (telegram_id, username, first_name, role, is_active, last_seen_at)
           VALUES (?, ?, ?, 'admin', 1, ?)
           ON CONFLICT(telegram_id) DO UPDATE SET
               username = COALESCE(excluded.username, admins.username),
               first_name = COALESCE(excluded.first_name, admins.first_name),
               last_seen_at = excluded.last_seen_at;""",
        (telegram_id, username, first_name, now)
    )

async def list_admins() -> list[dict]:
    return await db.fetch_all("SELECT * FROM admins ORDER BY id ASC;")

# ========================================================
# CUSTOMER OPERATIONS
# ========================================================

async def get_or_create_customer(telegram_user_id: int, username: str = None, full_name: str = None, telegram_username: str = None) -> dict:
    actual_username = telegram_username if telegram_username is not None else username
    row = await db.fetch_one("SELECT * FROM customers WHERE telegram_user_id = ?;", (telegram_user_id,))
    if not row:
        cust_id = await db.execute(
            """INSERT INTO customers (telegram_user_id, telegram_username, full_name)
               VALUES (?, ?, ?);""",
            (telegram_user_id, actual_username, full_name)
        )
        return await db.fetch_one("SELECT * FROM customers WHERE customer_id = ?;", (cust_id,))
    else:
        # Update username/full_name if provided and changed
        if actual_username or full_name:
            await db.execute(
                """UPDATE customers SET 
                   telegram_username = COALESCE(?, telegram_username),
                   full_name = COALESCE(?, full_name)
                   WHERE customer_id = ?;""",
                (actual_username, full_name, row["customer_id"])
            )
        return row

async def get_customer_by_id(customer_id: int) -> dict | None:
    return await db.fetch_one("SELECT * FROM customers WHERE customer_id = ?;", (customer_id,))

async def get_customer_by_telegram_id(telegram_user_id: int) -> dict | None:
    return await db.fetch_one("SELECT * FROM customers WHERE telegram_user_id = ?;", (telegram_user_id,))

async def update_customer_delivery_info(
    telegram_user_id: int,
    full_name: str,
    phone: str,
    city: str,
    area: str,
    sub_city: str = "",
    address: str = "",
    landmark: str = "",
    latitude: float = None,
    longitude: float = None
):
    await db.execute(
        """UPDATE customers SET
           full_name = ?, phone = ?, city = ?, area = ?, sub_city = ?,
           address = ?, landmark = ?, latitude = ?, longitude = ?
           WHERE telegram_user_id = ?;""",
        (full_name, phone, city, area, sub_city, address, landmark, latitude, longitude, telegram_user_id)
    )

async def search_customers(query: str, limit: int = 20) -> list[dict]:
    pattern = f"%{query}%"
    return await db.fetch_all(
        """SELECT * FROM customers 
           WHERE full_name LIKE ? OR telegram_username LIKE ? OR phone LIKE ? OR telegram_user_id LIKE ?
           ORDER BY customer_id DESC LIMIT ?;""",
        (pattern, pattern, pattern, pattern, limit)
    )

async def get_customer_stats(customer_id: int) -> dict:
    orders_row = await db.fetch_one(
        "SELECT COUNT(*) as count, COALESCE(SUM(total), 0) as total_spent FROM orders WHERE customer_id = ?;",
        (customer_id,)
    )
    return {
        "order_count": orders_row["count"] if orders_row else 0,
        "total_spent": orders_row["total_spent"] if orders_row else 0.0
    }

# ========================================================
# CATEGORY OPERATIONS
# ========================================================

async def get_all_categories(active_only: bool = True) -> list[dict]:
    query = "SELECT * FROM categories"
    if active_only:
        query += " WHERE is_active = 1"
    query += " ORDER BY display_order ASC, name ASC;"
    return await db.fetch_all(query)

async def get_category_by_id(category_id: int) -> dict | None:
    return await db.fetch_one("SELECT * FROM categories WHERE category_id = ?;", (category_id,))

async def get_category_by_slug(slug: str) -> dict | None:
    return await db.fetch_one("SELECT * FROM categories WHERE slug = ?;", (slug,))

async def create_category(name: str, slug: str, icon: str = "", description: str = "", display_order: int = 0) -> int:
    return await db.execute(
        """INSERT INTO categories (name, slug, icon, description, display_order, is_active)
           VALUES (?, ?, ?, ?, ?, 1);""",
        (name, slug, icon, description, display_order)
    )

async def update_category(category_id: int, name: str, slug: str, icon: str, description: str, is_active: int = 1):
    await db.execute(
        """UPDATE categories SET name = ?, slug = ?, icon = ?, description = ?, is_active = ?
           WHERE category_id = ?;""",
        (name, slug, icon, description, is_active, category_id)
    )

async def delete_category(category_id: int):
    await db.execute("DELETE FROM categories WHERE category_id = ?;", (category_id,))

# ========================================================
# PRODUCT OPERATIONS
# ========================================================

async def get_product_by_id(product_id: int) -> dict | None:
    prod = await db.fetch_one(
        """SELECT p.*, c.name as category_name, c.icon as category_icon 
           FROM products p 
           LEFT JOIN categories c ON p.category_id = c.category_id 
           WHERE p.product_id = ?;""",
        (product_id,)
    )
    if prod:
        prod["images"] = await get_product_images(product_id)
    return prod

async def get_product_by_source(channel: str, message_id: int) -> dict | None:
    return await db.fetch_one(
        "SELECT * FROM products WHERE source_channel = ? AND source_message_id = ?;",
        (channel, message_id)
    )

async def list_products(
    category_id: int = None,
    category_slug: str = None,
    search: str = None,
    availability: str = None,
    condition: str = None,
    brand: str = None,
    storage: str = None,
    color: str = None,
    ram: str = None,
    min_price: float = None,
    max_price: float = None,
    featured_only: bool = False,
    new_arrivals_only: bool = False,
    offers_only: bool = False,
    approval_status: str = "Published",
    admin_view: bool = False,
    offset: int = 0,
    limit: int = 10
) -> tuple[list[dict], int]:
    conditions = []
    params = []

    if not admin_view:
        if approval_status:
            conditions.append("p.approval_status = ?")
            params.append(approval_status)
        # Exclude Hidden products from customer view
        conditions.append("p.availability != 'Hidden'")

    if category_id:
        conditions.append("p.category_id = ?")
        params.append(category_id)
    elif category_slug:
        if category_slug == "new_arrivals":
            conditions.append("p.new_arrival = 1")
        elif category_slug == "offers":
            conditions.append("(p.discount_price IS NOT NULL AND p.discount_price > 0)")
        else:
            conditions.append("c.slug = ?")
            params.append(category_slug)

    if availability:
        conditions.append("p.availability = ?")
        params.append(availability)

    if condition:
        conditions.append("p.condition LIKE ?")
        params.append(f"%{condition}%")

    if brand:
        conditions.append("p.brand LIKE ?")
        params.append(f"%{brand}%")

    if storage:
        conditions.append("p.storage LIKE ?")
        params.append(f"%{storage}%")

    if color:
        conditions.append("p.color LIKE ?")
        params.append(f"%{color}%")

    if ram:
        conditions.append("p.ram LIKE ?")
        params.append(f"%{ram}%")

    if min_price is not None:
        conditions.append("COALESCE(p.discount_price, p.price) >= ?")
        params.append(min_price)

    if max_price is not None:
        conditions.append("COALESCE(p.discount_price, p.price) <= ?")
        params.append(max_price)

    if featured_only:
        conditions.append("p.featured = 1")

    if new_arrivals_only:
        conditions.append("p.new_arrival = 1")

    if offers_only:
        conditions.append("(p.discount_price IS NOT NULL AND p.discount_price > 0)")

    if search:
        search_pattern = f"%{search}%"
        conditions.append("""(p.name LIKE ? OR p.brand LIKE ? OR p.model LIKE ? 
                             OR p.description LIKE ? OR p.storage LIKE ? OR p.color LIKE ?)""")
        params.extend([search_pattern] * 6)

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    # Count total
    count_query = f"""SELECT COUNT(*) as total 
                      FROM products p 
                      LEFT JOIN categories c ON p.category_id = c.category_id 
                      {where_clause};"""
    count_row = await db.fetch_one(count_query, tuple(params))
    total = count_row["total"] if count_row else 0

    # Query items with pagination
    query = f"""SELECT p.*, c.name as category_name, c.icon as category_icon,
                       (SELECT file_path FROM product_images WHERE product_id = p.product_id ORDER BY is_primary DESC, image_id ASC LIMIT 1) as primary_image
                FROM products p 
                LEFT JOIN categories c ON p.category_id = c.category_id 
                {where_clause}
                ORDER BY p.new_arrival DESC, p.featured DESC, p.created_at DESC
                LIMIT ? OFFSET ?;"""
    
    query_params = list(params) + [limit, offset]
    rows = await db.fetch_all(query, tuple(query_params))

    # Attach images to products
    for r in rows:
        r["images"] = await get_product_images(r["product_id"])

    return rows, total

async def create_product(
    name: str,
    category_id: int = None,
    brand: str = None,
    model: str = None,
    description: str = "",
    price: float = None,
    currency: str = "ETB",
    condition: str = None,
    storage: str = None,
    ram: str = None,
    color: str = None,
    battery_health: str = None,
    stock_quantity: int = 1,
    availability: str = "Available",
    approval_status: str = "Published",
    featured: int = 0,
    new_arrival: int = 0,
    discount_price: float = None,
    discount_percentage: float = None,
    source_channel: str = None,
    source_channel_id: str = None,
    source_message_id: int = None,
    source_message_url: str = None,
    source_message_date: str = None,
    parse_confidence: float = 1.0
) -> int:
    query = """
        INSERT INTO products (
            name, category_id, brand, model, description, price, currency,
            condition, storage, ram, color, battery_health, stock_quantity,
            availability, approval_status, featured, new_arrival,
            discount_price, discount_percentage, source_channel, source_channel_id,
            source_message_id, source_message_url, source_message_date, parse_confidence
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """
    return await db.execute(query, (
        name, category_id, brand, model, description, price, currency,
        condition, storage, ram, color, battery_health, stock_quantity,
        availability, approval_status, featured, new_arrival,
        discount_price, discount_percentage, source_channel, source_channel_id,
        source_message_id, source_message_url, source_message_date, parse_confidence
    ))

ALLOWED_PRODUCT_FIELDS = {
    "name", "category_id", "brand", "model", "description", "price", "currency",
    "condition", "storage", "ram", "color", "battery_health", "stock_quantity",
    "availability", "approval_status", "featured", "new_arrival", "discount_price",
    "discount_percentage", "source_channel", "source_channel_id", "source_message_id",
    "source_message_url", "source_message_date", "parse_confidence", "updated_at"
}

ALLOWED_DELIVERY_FIELDS = {
    "status", "delivery_person", "delivery_phone", "delivery_note",
    "dispatch_time", "delivered_time", "updated_at"
}

async def update_product(product_id: int, **fields) -> None:
    valid_fields = {k: v for k, v in fields.items() if k in ALLOWED_PRODUCT_FIELDS}
    if not valid_fields:
        return
    valid_fields["updated_at"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    set_clause = ", ".join([f"{k} = ?" for k in valid_fields.keys()])
    query = f"UPDATE products SET {set_clause} WHERE product_id = ?;"
    params = list(valid_fields.values()) + [product_id]
    await db.execute(query, tuple(params))

async def update_product_availability(product_id: int, availability: str):
    await update_product(product_id, availability=availability)

async def update_product_price(product_id: int, price: float, discount_price: float = None):
    disc_pct = None
    if discount_price and price and price > 0:
        disc_pct = round(((price - discount_price) / price) * 100, 1)
    await update_product(product_id, price=price, discount_price=discount_price, discount_percentage=disc_pct)

async def update_product_stock(product_id: int, stock_quantity: int):
    avail = "Available"
    if stock_quantity <= 0:
        avail = "Out of Stock"
    elif stock_quantity < 3:
        avail = "Low Stock"
    await update_product(product_id, stock_quantity=stock_quantity, availability=avail)

async def delete_product(product_id: int):
    await db.execute("DELETE FROM products WHERE product_id = ?;", (product_id,))

# ========================================================
# PRODUCT IMAGES
# ========================================================

async def get_product_images(product_id: int) -> list[dict]:
    return await db.fetch_all(
        "SELECT * FROM product_images WHERE product_id = ? ORDER BY is_primary DESC, display_order ASC, image_id ASC;",
        (product_id,)
    )

async def add_product_image(product_id: int, file_path: str, is_primary: int = 0, file_url: str = None, telegram_file_id: str = None) -> int:
    return await db.execute(
        """INSERT INTO product_images (product_id, file_path, file_url, telegram_file_id, is_primary)
           VALUES (?, ?, ?, ?, ?);""",
        (product_id, file_path, file_url, telegram_file_id, is_primary)
    )

async def delete_product_image(image_id: int):
    await db.execute("DELETE FROM product_images WHERE image_id = ?;", (image_id,))

# ========================================================
# ORDER OPERATIONS
# ========================================================

def generate_order_number() -> str:
    now = datetime.utcnow()
    rand_suffix = now.strftime("%f")[:4]
    return f"ISW-{now.strftime('%y%m%d')}-{rand_suffix}"

async def create_order(
    customer_id: int,
    items: list[dict],
    delivery_info: dict,
    delivery_fee: float = 0.0
) -> dict:
    order_number = generate_order_number()
    subtotal = sum(item["unit_price"] * item["quantity"] for item in items)
    total = subtotal + delivery_fee

    lat = delivery_info.get("latitude")
    lng = delivery_info.get("longitude")
    addr = delivery_info.get("address", "")
    if lat is not None and lng is not None and "maps.google.com" not in addr:
        maps_link = f"https://maps.google.com/?q={lat},{lng}"
        if addr:
            addr = f"{addr} (📍 {maps_link})"
        else:
            addr = f"📍 GPS Pin: {maps_link}"

    order_id = await db.execute(
        """INSERT INTO orders (
            order_number, customer_id, subtotal, delivery_fee, total, currency,
            order_status, payment_status, delivery_name, delivery_phone,
            delivery_city, delivery_area, delivery_sub_city, delivery_address,
            delivery_landmark, delivery_note, delivery_latitude, delivery_longitude
        ) VALUES (?, ?, ?, ?, ?, 'ETB', 'Pending', 'Pending', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);""",
        (
            order_number, customer_id, subtotal, delivery_fee, total,
            delivery_info.get("full_name"),
            delivery_info.get("phone"),
            delivery_info.get("city"),
            delivery_info.get("area"),
            delivery_info.get("sub_city", ""),
            addr,
            delivery_info.get("landmark", ""),
            delivery_info.get("note", ""),
            lat,
            lng
        )
    )

    for item in items:
        tot = item["unit_price"] * item["quantity"]
        await db.execute(
            """INSERT INTO order_items (order_id, product_id, product_name, unit_price, quantity, total_price)
               VALUES (?, ?, ?, ?, ?, ?);""",
            (order_id, item.get("product_id"), item["product_name"], item["unit_price"], item["quantity"], tot)
        )
        # Deduct stock if product_id is set
        if item.get("product_id"):
            await db.execute(
                """UPDATE products 
                   SET stock_quantity = MAX(0, stock_quantity - ?)
                   WHERE product_id = ?;""",
                (item["quantity"], item["product_id"])
            )

    # Initialize Delivery record
    await db.execute(
        """INSERT INTO deliveries (order_id, status, delivery_note)
           VALUES (?, 'Pending', ?);""",
        (order_id, delivery_info.get("note", ""))
    )

    # Initialize Payment record
    payment_method = delivery_info.get("payment_method", "Bank Transfer")
    await db.execute(
        """INSERT INTO payments (order_id, payment_method, amount, currency, status)
           VALUES (?, ?, ?, 'ETB', 'Pending');""",
        (order_id, payment_method, total)
    )

    # Update customer's last order timestamp
    await db.execute(
        "UPDATE customers SET last_order_at = CURRENT_TIMESTAMP WHERE customer_id = ?;",
        (customer_id,)
    )

    return await get_order_by_id(order_id)

async def get_order_by_id(order_id: int) -> dict | None:
    order = await db.fetch_one(
        """SELECT o.*, c.telegram_user_id, c.telegram_username, c.full_name as cust_name, c.phone as cust_phone
           FROM orders o
           JOIN customers c ON o.customer_id = c.customer_id
           WHERE o.order_id = ?;""",
        (order_id,)
    )
    if order:
        order["items"] = await get_order_items(order_id)
        order["payment"] = await get_payment_for_order(order_id)
        order["receipts"] = await get_receipts_for_order(order_id)
        order["delivery"] = await get_delivery_for_order(order_id)
    return order

async def get_order_by_number(order_number: str) -> dict | None:
    row = await db.fetch_one("SELECT order_id FROM orders WHERE order_number = ?;", (order_number,))
    if row:
        return await get_order_by_id(row["order_id"])
    return None

async def get_order_items(order_id: int) -> list[dict]:
    return await db.fetch_all("SELECT * FROM order_items WHERE order_id = ?;", (order_id,))

async def list_orders_for_customer(customer_id: int, limit: int = 10) -> list[dict]:
    orders = await db.fetch_all(
        "SELECT * FROM orders WHERE customer_id = ? ORDER BY order_id DESC LIMIT ?;",
        (customer_id, limit)
    )
    for o in orders:
        o["items"] = await get_order_items(o["order_id"])
        o["receipts"] = await get_receipts_for_order(o["order_id"])
    return orders

async def list_orders_admin(
    status: str = None,
    payment_status: str = None,
    query: str = None,
    offset: int = 0,
    limit: int = 20
) -> tuple[list[dict], int]:
    conds = []
    params = []

    if status and status != "All":
        conds.append("o.order_status = ?")
        params.append(status)

    if payment_status and payment_status != "All":
        conds.append("o.payment_status = ?")
        params.append(payment_status)

    if query:
        qp = f"%{query}%"
        conds.append("""(o.order_number LIKE ? OR o.delivery_name LIKE ? 
                         OR o.delivery_phone LIKE ? OR c.telegram_username LIKE ? OR c.full_name LIKE ?)""")
        params.extend([qp] * 5)

    where_sql = f"WHERE {' AND '.join(conds)}" if conds else ""

    cnt_row = await db.fetch_one(
        f"""SELECT COUNT(*) as cnt FROM orders o 
           JOIN customers c ON o.customer_id = c.customer_id {where_sql};""",
        tuple(params)
    )
    total = cnt_row["cnt"] if cnt_row else 0

    orders_sql = f"""
        SELECT o.*, c.telegram_user_id, c.telegram_username, c.full_name as customer_name, c.phone as customer_phone
        FROM orders o
        JOIN customers c ON o.customer_id = c.customer_id
        {where_sql}
        ORDER BY o.order_id DESC
        LIMIT ? OFFSET ?;
    """
    rows = await db.fetch_all(orders_sql, tuple(params + [limit, offset]))
    for r in rows:
        r["items"] = await get_order_items(r["order_id"])
        r["payment"] = await get_payment_for_order(r["order_id"])
        r["receipts"] = await get_receipts_for_order(r["order_id"])
        r["delivery"] = await get_delivery_for_order(r["order_id"])
    return rows, total

async def update_order_status(order_id: int, new_status: str, admin_notes: str = None):
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    if admin_notes:
        await db.execute(
            "UPDATE orders SET order_status = ?, admin_notes = ?, updated_at = ? WHERE order_id = ?;",
            (new_status, admin_notes, now, order_id)
        )
    else:
        await db.execute(
            "UPDATE orders SET order_status = ?, updated_at = ? WHERE order_id = ?;",
            (new_status, now, order_id)
        )

async def update_admin_notes(order_id: int, notes: str):
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    await db.execute(
        "UPDATE orders SET admin_notes = ?, updated_at = ? WHERE order_id = ?;",
        (notes, now, order_id)
    )

# ========================================================
# PAYMENT & RECEIPT OPERATIONS
# ========================================================

async def create_payment(order_id: int, payment_method: str, amount: float) -> int:
    return await db.execute(
        """INSERT INTO payments (order_id, payment_method, amount, currency, status)
           VALUES (?, ?, ?, 'ETB', 'Pending');""",
        (order_id, payment_method, amount)
    )

async def get_payment_for_order(order_id: int) -> dict | None:
    return await db.fetch_one("SELECT * FROM payments WHERE order_id = ? ORDER BY payment_id DESC LIMIT 1;", (order_id,))

async def add_receipt(
    order_id: int,
    customer_id: int,
    payment_id: int,
    file_path: str,
    file_type: str,
    file_size: int,
    telegram_file_id: str = None
) -> int:
    receipt_id = await db.execute(
        """INSERT INTO receipts (order_id, customer_id, payment_id, file_path, file_type, file_size, telegram_file_id, verification_status)
           VALUES (?, ?, ?, ?, ?, ?, ?, 'Pending');""",
        (order_id, customer_id, payment_id, file_path, file_type, file_size, telegram_file_id)
    )

    # Update payment status to Uploaded
    if payment_id:
        await db.execute("UPDATE payments SET status = 'Uploaded' WHERE payment_id = ?;", (payment_id,))
    await db.execute("UPDATE orders SET payment_status = 'Uploaded', order_status = 'Payment Pending' WHERE order_id = ?;", (order_id,))

    return receipt_id

async def update_receipt_file_path(receipt_id: int, file_path: str):
    await db.execute("UPDATE receipts SET file_path = ? WHERE receipt_id = ?;", (file_path, receipt_id))

async def get_receipts_for_order(order_id: int) -> list[dict]:
    return await db.fetch_all("SELECT * FROM receipts WHERE order_id = ? ORDER BY receipt_id DESC;", (order_id,))

async def verify_payment(order_id: int, admin_id: int, approved: bool, reason: str = None):
    status = "Verified" if approved else "Rejected"
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    # Update payment
    await db.execute(
        """UPDATE payments SET status = ?, rejection_reason = ?, verified_by_admin_id = ?, verified_at = ?
           WHERE order_id = ?;""",
        (status, reason if not approved else None, admin_id, now, order_id)
    )

    # Update receipts
    await db.execute(
        "UPDATE receipts SET verification_status = ? WHERE order_id = ?;",
        (status, order_id)
    )

    # Update order
    new_order_status = "Payment Confirmed" if approved else "Payment Pending"
    await db.execute(
        "UPDATE orders SET payment_status = ?, order_status = ?, updated_at = ? WHERE order_id = ?;",
        (status, new_order_status, now, order_id)
    )

# ========================================================
# DELIVERY OPERATIONS
# ========================================================

async def get_delivery_for_order(order_id: int) -> dict | None:
    return await db.fetch_one("SELECT * FROM deliveries WHERE order_id = ?;", (order_id,))

async def update_delivery_status(
    order_id: int,
    status: str,
    delivery_person: str = None,
    delivery_phone: str = None,
    note: str = None
):
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    deliv = await get_delivery_for_order(order_id)
    
    dispatch_time = now if status == "Out for Delivery" and (not deliv or not deliv.get("dispatch_time")) else None
    delivered_time = now if status == "Delivered" else None

    if not deliv:
        await db.execute(
            """INSERT INTO deliveries (order_id, status, delivery_person, delivery_phone, delivery_note, dispatch_time, delivered_time, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?);""",
            (order_id, status, delivery_person, delivery_phone, note, dispatch_time, delivered_time, now)
        )
    else:
        fields = {"status": status, "updated_at": now}
        if delivery_person:
            fields["delivery_person"] = delivery_person
        if delivery_phone:
            fields["delivery_phone"] = delivery_phone
        if note:
            fields["delivery_note"] = note
        if dispatch_time:
            fields["dispatch_time"] = dispatch_time
        if delivered_time:
            fields["delivered_time"] = delivered_time

        valid_fields = {k: v for k, v in fields.items() if k in ALLOWED_DELIVERY_FIELDS}
        set_clause = ", ".join([f"{k} = ?" for k in valid_fields.keys()])
        await db.execute(f"UPDATE deliveries SET {set_clause} WHERE order_id = ?;", tuple(list(valid_fields.values()) + [order_id]))

    # Map to order_status if relevant
    if status == "Out for Delivery":
        await db.execute("UPDATE orders SET order_status = 'Out for Delivery', updated_at = ? WHERE order_id = ?;", (now, order_id))
    elif status == "Delivered":
        await db.execute("UPDATE orders SET order_status = 'Delivered', updated_at = ? WHERE order_id = ?;", (now, order_id))

# ========================================================
# SYSTEM SETTINGS OPERATIONS
# ========================================================

async def get_setting(key: str, default: str = "") -> str:
    row = await db.fetch_one("SELECT value FROM system_settings WHERE key = ?;", (key,))
    return row["value"] if row else default

async def set_setting(key: str, value: str, description: str = ""):
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    await db.execute(
        """INSERT INTO system_settings (key, value, description, updated_at)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at;""",
        (key, value, description, now)
    )

async def get_all_settings() -> dict[str, str]:
    rows = await db.fetch_all("SELECT key, value FROM system_settings;")
    return {r["key"]: r["value"] for r in rows}

async def get_payment_methods() -> list[dict]:
    raw = await get_setting("payment_methods", "[]")
    try:
        return json.loads(raw)
    except Exception:
        return []

async def save_payment_methods(methods: list[dict]):
    await set_setting("payment_methods", json.dumps(methods, ensure_ascii=False), "Admin configured payment methods")

# ========================================================
# AUDIT LOGGING
# ========================================================

async def log_audit_action(
    admin_id: int,
    action: str,
    target_type: str,
    target_id: str,
    prev_val: str = None,
    new_val: str = None,
    details: str = None
):
    await db.execute(
        """INSERT INTO audit_logs (admin_id, action, target_type, target_id, previous_value, new_value, details)
           VALUES (?, ?, ?, ?, ?, ?, ?);""",
        (admin_id, action, target_type, str(target_id), prev_val, new_val, details)
    )

async def get_recent_audit_logs(limit: int = 50) -> list[dict]:
    return await db.fetch_all("SELECT * FROM audit_logs ORDER BY log_id DESC LIMIT ?;", (limit,))

# ========================================================
# CHANNEL IMPORT & SYNC RECORDS
# ========================================================

async def record_channel_message(
    channel: str,
    message_id: int,
    message_date: str,
    text: str,
    media_ref: str = None,
    is_product: int = 0,
    product_id: int = None,
    status: str = "pending",
    error: str = None
):
    await db.execute(
        """INSERT INTO channel_messages (
            channel_username, message_id, message_date, message_text, media_file_reference,
            is_product, product_id, parse_status, error_message
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(channel_username, message_id) DO UPDATE SET
            message_text = excluded.message_text,
            is_product = excluded.is_product,
            product_id = COALESCE(excluded.product_id, channel_messages.product_id),
            parse_status = excluded.parse_status,
            error_message = excluded.error_message;""",
        (channel, message_id, message_date, text, media_ref, is_product, product_id, status, error)
    )

async def get_channel_sync_stats(channel: str) -> dict:
    scanned = await db.fetch_one("SELECT COUNT(*) as cnt FROM channel_messages WHERE channel_username = ?;", (channel,))
    detected = await db.fetch_one("SELECT COUNT(*) as cnt FROM channel_messages WHERE channel_username = ? AND is_product = 1;", (channel,))
    imported = await db.fetch_one("SELECT COUNT(*) as cnt FROM channel_messages WHERE channel_username = ? AND parse_status = 'imported';", (channel,))
    updated = await db.fetch_one("SELECT COUNT(*) as cnt FROM channel_messages WHERE channel_username = ? AND parse_status = 'updated';", (channel,))
    skipped = await db.fetch_one("SELECT COUNT(*) as cnt FROM channel_messages WHERE channel_username = ? AND parse_status = 'skipped';", (channel,))
    review = await db.fetch_one("SELECT COUNT(*) as cnt FROM channel_messages WHERE channel_username = ? AND parse_status = 'needs_review';", (channel,))
    errors = await db.fetch_one("SELECT COUNT(*) as cnt FROM channel_messages WHERE channel_username = ? AND parse_status = 'failed';", (channel,))
    img_cnt = await db.fetch_one("SELECT COUNT(*) as cnt FROM product_images WHERE product_id IN (SELECT product_id FROM products WHERE source_channel = ?);", (channel,))

    return {
        "messages_scanned": scanned["cnt"] if scanned else 0,
        "products_detected": detected["cnt"] if detected else 0,
        "products_imported": imported["cnt"] if imported else 0,
        "products_updated": updated["cnt"] if updated else 0,
        "products_skipped": skipped["cnt"] if skipped else 0,
        "products_needing_review": review["cnt"] if review else 0,
        "images_imported": img_cnt["cnt"] if img_cnt else 0,
        "import_errors": errors["cnt"] if errors else 0
    }

async def get_sync_stats(channel: str = None) -> dict:
    if not channel:
        channel = await get_setting("channel_username", "@iSwitch0")
    return await get_channel_sync_stats(channel)

async def get_last_scanned_message_id(channel: str) -> int:
    row = await db.fetch_one("SELECT last_scanned_message_id FROM channel_sources WHERE channel_username = ?;", (channel,))
    return row["last_scanned_message_id"] if row else 0

async def set_last_scanned_message_id(channel: str, message_id: int):
    await db.execute(
        """INSERT INTO channel_sources (channel_username, last_scanned_message_id)
           VALUES (?, ?)
           ON CONFLICT(channel_username) DO UPDATE SET last_scanned_message_id = MAX(channel_sources.last_scanned_message_id, excluded.last_scanned_message_id);""",
        (channel, message_id)
    )

async def get_review_queue(offset: int = 0, limit: int = 20) -> tuple[list[dict], int]:
    cnt = await db.fetch_one("SELECT COUNT(*) as cnt FROM channel_messages WHERE parse_status = 'needs_review';")
    total = cnt["cnt"] if cnt else 0
    rows = await db.fetch_all(
        "SELECT * FROM channel_messages WHERE parse_status = 'needs_review' ORDER BY message_id DESC LIMIT ? OFFSET ?;",
        (limit, offset)
    )
    return rows, total

# ========================================================
# DASHBOARD REPORTING
# ========================================================

async def get_dashboard_metrics() -> dict:
    total_prods = await db.fetch_one("SELECT COUNT(*) as cnt FROM products;")
    avail_prods = await db.fetch_one("SELECT COUNT(*) as cnt FROM products WHERE availability = 'Available';")
    sold_prods = await db.fetch_one("SELECT COUNT(*) as cnt FROM products WHERE availability = 'Sold';")
    out_prods = await db.fetch_one("SELECT COUNT(*) as cnt FROM products WHERE availability = 'Out of Stock';")

    total_orders = await db.fetch_one("SELECT COUNT(*) as cnt FROM orders;")
    pending_orders = await db.fetch_one("SELECT COUNT(*) as cnt FROM orders WHERE order_status IN ('Pending', 'Payment Pending', 'Preparing');")
    completed_orders = await db.fetch_one("SELECT COUNT(*) as cnt FROM orders WHERE order_status = 'Delivered';")

    pending_payments = await db.fetch_one("SELECT COUNT(*) as cnt FROM payments WHERE status IN ('Pending', 'Uploaded');")
    verified_payments = await db.fetch_one("SELECT COUNT(*) as cnt FROM payments WHERE status = 'Verified';")
    total_sales = await db.fetch_one("SELECT COALESCE(SUM(total), 0) as total FROM orders WHERE payment_status = 'Verified';")

    cat_dist = await db.fetch_all(
        """SELECT COALESCE(c.name, 'Uncategorized') as name, COUNT(p.product_id) as count
           FROM products p
           LEFT JOIN categories c ON p.category_id = c.category_id
           GROUP BY c.name ORDER BY count DESC;"""
    )

    status_dist = await db.fetch_all(
        """SELECT order_status, COUNT(*) as count FROM orders GROUP BY order_status;"""
    )

    return {
        "total_products": total_prods["cnt"] if total_prods else 0,
        "available_products": avail_prods["cnt"] if avail_prods else 0,
        "sold_products": sold_prods["cnt"] if sold_prods else 0,
        "out_of_stock": out_prods["cnt"] if out_prods else 0,
        "total_orders": total_orders["cnt"] if total_orders else 0,
        "pending_orders": pending_orders["cnt"] if pending_orders else 0,
        "completed_orders": completed_orders["cnt"] if completed_orders else 0,
        "pending_payments": pending_payments["cnt"] if pending_payments else 0,
        "verified_payments": verified_payments["cnt"] if verified_payments else 0,
        "total_sales": total_sales["total"] if total_sales else 0.0,
        "category_distribution": cat_dist,
        "order_status_distribution": status_dist
    }
