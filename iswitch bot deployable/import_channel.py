import sys
import asyncio
import logging
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from database.db import db
from database.crud import seed_initial_data, get_channel_sync_stats, list_products
from services.importer import channel_importer
from config import TELEGRAM_CHANNEL

logging.basicConfig(level=logging.INFO, format="%(asctime)s - [%(levelname)s] - %(message)s")
logger = logging.getLogger("iswitch.import_cli")

async def main():
    print("==================================================")
    print(f"  Starting Channel Product Import for {TELEGRAM_CHANNEL}")
    print("==================================================")

    # 1. Initialize Database
    await db.init_db()
    await seed_initial_data()

    # 2. Progress display callback
    async def on_progress(p):
        curr_msg = p["current_message_id"]
        scanned = p["total_scanned"]
        imported = p["products_imported"]
        updated = p["products_updated"]
        prod_name = p["current_product_name"]
        print(f"\r[Msg #{curr_msg}] Scanned: {scanned} | Imported: {imported} | Updated: {updated} | Current: {prod_name[:25]}", end="", flush=True)

    channel_importer.set_progress_callback(on_progress)

    # 3. Run import
    print("Connecting to channel stream and scanning historical posts...\n")
    res = await channel_importer.import_from_web_pagination(max_pages=15, delay_seconds=0.5)

    print("\n\n==================================================")
    print("                IMPORT SUMMARY                    ")
    print("==================================================")
    stats = await get_channel_sync_stats(TELEGRAM_CHANNEL)
    print(f"• Total Messages Scanned: {stats['messages_scanned']}")
    print(f"• Products Detected:      {stats['products_detected']}")
    print(f"• Products Imported:      {stats['products_imported']}")
    print(f"• Products Updated:       {stats['products_updated']}")
    print(f"• Messages Skipped:       {stats['products_skipped']}")
    print(f"• Needing Review:         {stats['products_needing_review']}")
    print(f"• Product Images Saved:   {stats['images_imported']}")
    print(f"• Errors:                 {stats['import_errors']}")
    print("==================================================\n")

    # List some imported products from the DB
    prods, total = await list_products(limit=5, admin_view=True)
    if prods:
        print(f"Preview of {min(5, total)} products in catalog:")
        for p in prods:
            price = p.get('discount_price') or p.get('price') or 0
            print(f"  - [{p['product_id']}] {p['name']} | {price:,.0f} ETB | Stock: {p['stock_quantity']} ({p['availability']})")
    print()

if __name__ == "__main__":
    asyncio.run(main())
