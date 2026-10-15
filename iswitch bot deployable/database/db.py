import aiosqlite
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from config import DB_PATH

logger = logging.getLogger("iswitch.db")

class Database:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path

    @asynccontextmanager
    async def connection(self):
        conn = await aiosqlite.connect(self.db_path)
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys = ON;")
        await conn.execute("PRAGMA journal_mode = WAL;")
        try:
            yield conn
        finally:
            await conn.close()

    async def execute(self, query: str, parameters: tuple = ()) -> int:
        async with self.connection() as conn:
            cursor = await conn.execute(query, parameters)
            await conn.commit()
            return cursor.lastrowid

    async def execute_many(self, query: str, seq_of_parameters: list) -> None:
        async with self.connection() as conn:
            await conn.executemany(query, seq_of_parameters)
            await conn.commit()

    async def fetch_one(self, query: str, parameters: tuple = ()) -> dict | None:
        async with self.connection() as conn:
            async with conn.execute(query, parameters) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def fetch_all(self, query: str, parameters: tuple = ()) -> list[dict]:
        async with self.connection() as conn:
            async with conn.execute(query, parameters) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def init_db(self):
        """Creates all required tables, indexes, and initial seeds if not present."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        async with self.connection() as conn:
            # Admins table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS admins (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id INTEGER UNIQUE NOT NULL,
                    username TEXT,
                    first_name TEXT,
                    role TEXT DEFAULT 'admin',
                    is_active INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # Customers table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS customers (
                    customer_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_user_id INTEGER UNIQUE NOT NULL,
                    telegram_username TEXT,
                    full_name TEXT,
                    phone TEXT,
                    city TEXT,
                    area TEXT,
                    sub_city TEXT,
                    address TEXT,
                    landmark TEXT,
                    latitude REAL,
                    longitude REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_order_at TIMESTAMP
                );
            """)

            # Categories table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS categories (
                    category_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    slug TEXT UNIQUE NOT NULL,
                    icon TEXT,
                    description TEXT,
                    display_order INTEGER DEFAULT 0,
                    is_active INTEGER DEFAULT 1
                );
            """)

            # Products table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS products (
                    product_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    category_id INTEGER REFERENCES categories(category_id) ON DELETE SET NULL,
                    brand TEXT,
                    model TEXT,
                    description TEXT,
                    price REAL,
                    currency TEXT DEFAULT 'ETB',
                    condition TEXT,
                    storage TEXT,
                    ram TEXT,
                    color TEXT,
                    battery_health TEXT,
                    stock_quantity INTEGER DEFAULT 1,
                    availability TEXT DEFAULT 'Available',
                    approval_status TEXT DEFAULT 'Published',
                    featured INTEGER DEFAULT 0,
                    new_arrival INTEGER DEFAULT 0,
                    discount_price REAL,
                    discount_percentage REAL,
                    source_channel TEXT,
                    source_channel_id TEXT,
                    source_message_id INTEGER,
                    source_message_url TEXT,
                    source_message_date TIMESTAMP,
                    parse_confidence REAL DEFAULT 1.0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(source_channel, source_message_id)
                );
            """)

            # Product images table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS product_images (
                    image_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_id INTEGER NOT NULL REFERENCES products(product_id) ON DELETE CASCADE,
                    file_path TEXT NOT NULL,
                    file_url TEXT,
                    telegram_file_id TEXT,
                    is_primary INTEGER DEFAULT 0,
                    display_order INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # Orders table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    order_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_number TEXT UNIQUE NOT NULL,
                    customer_id INTEGER NOT NULL REFERENCES customers(customer_id),
                    subtotal REAL NOT NULL,
                    delivery_fee REAL DEFAULT 0.0,
                    total REAL NOT NULL,
                    currency TEXT DEFAULT 'ETB',
                    order_status TEXT DEFAULT 'Pending',
                    payment_status TEXT DEFAULT 'Pending',
                    delivery_name TEXT,
                    delivery_phone TEXT,
                    delivery_city TEXT,
                    delivery_area TEXT,
                    delivery_sub_city TEXT,
                    delivery_address TEXT,
                    delivery_landmark TEXT,
                    delivery_note TEXT,
                    delivery_latitude REAL,
                    delivery_longitude REAL,
                    admin_notes TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # Order items table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS order_items (
                    item_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id INTEGER NOT NULL REFERENCES orders(order_id) ON DELETE CASCADE,
                    product_id INTEGER REFERENCES products(product_id) ON DELETE SET NULL,
                    product_name TEXT NOT NULL,
                    unit_price REAL NOT NULL,
                    quantity INTEGER NOT NULL,
                    total_price REAL NOT NULL
                );
            """)

            # Payments table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS payments (
                    payment_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id INTEGER NOT NULL REFERENCES orders(order_id) ON DELETE CASCADE,
                    payment_method TEXT NOT NULL,
                    amount REAL NOT NULL,
                    currency TEXT DEFAULT 'ETB',
                    status TEXT DEFAULT 'Pending',
                    rejection_reason TEXT,
                    verified_by_admin_id INTEGER,
                    verified_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # Receipts table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS receipts (
                    receipt_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id INTEGER NOT NULL REFERENCES orders(order_id) ON DELETE CASCADE,
                    customer_id INTEGER NOT NULL REFERENCES customers(customer_id),
                    payment_id INTEGER REFERENCES payments(payment_id),
                    file_path TEXT NOT NULL,
                    file_type TEXT NOT NULL,
                    file_size INTEGER NOT NULL,
                    telegram_file_id TEXT,
                    verification_status TEXT DEFAULT 'Pending',
                    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # Deliveries table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS deliveries (
                    delivery_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id INTEGER UNIQUE NOT NULL REFERENCES orders(order_id) ON DELETE CASCADE,
                    status TEXT DEFAULT 'Pending',
                    delivery_person TEXT,
                    delivery_phone TEXT,
                    delivery_note TEXT,
                    dispatch_time TIMESTAMP,
                    delivered_time TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # Announcements table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS announcements (
                    announcement_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    admin_id INTEGER,
                    title TEXT,
                    content TEXT NOT NULL,
                    target_type TEXT DEFAULT 'all',
                    target_id INTEGER,
                    sent_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # Notifications log
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS notifications (
                    notification_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    recipient_telegram_id INTEGER NOT NULL,
                    message TEXT NOT NULL,
                    notification_type TEXT,
                    is_sent INTEGER DEFAULT 0,
                    sent_at TIMESTAMP
                );
            """)

            # Channel sources table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS channel_sources (
                    source_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel_username TEXT UNIQUE NOT NULL,
                    channel_title TEXT,
                    channel_id TEXT,
                    last_scanned_message_id INTEGER DEFAULT 0,
                    is_active INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # Channel raw message audit
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS channel_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel_username TEXT NOT NULL,
                    channel_id TEXT,
                    message_id INTEGER NOT NULL,
                    message_date TIMESTAMP,
                    message_text TEXT,
                    media_file_reference TEXT,
                    is_product INTEGER DEFAULT 0,
                    product_id INTEGER REFERENCES products(product_id) ON DELETE SET NULL,
                    parse_status TEXT DEFAULT 'pending',
                    error_message TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(channel_username, message_id)
                );
            """)

            # System settings
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS system_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    description TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # Audit logs table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_logs (
                    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    admin_id INTEGER,
                    action TEXT NOT NULL,
                    target_type TEXT,
                    target_id TEXT,
                    previous_value TEXT,
                    new_value TEXT,
                    details TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # Create Indexes for fast querying
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_products_category ON products(category_id);")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_products_availability ON products(availability);")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_products_source ON products(source_channel, source_message_id);")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_customer ON orders(customer_id);")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(order_status);")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_customers_tgid ON customers(telegram_user_id);")

            # Migration: Ensure delivery_latitude and delivery_longitude exist on orders
            try:
                await conn.execute("ALTER TABLE orders ADD COLUMN delivery_latitude REAL;")
            except Exception:
                pass
            try:
                await conn.execute("ALTER TABLE orders ADD COLUMN delivery_longitude REAL;")
            except Exception:
                pass

            await conn.commit()

        logger.info("Database schema initialized successfully.")

# Global instance
db = Database()
