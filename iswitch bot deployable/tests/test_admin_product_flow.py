import unittest
import asyncio
from pathlib import Path
import sys

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from admin_bot.handlers.products import (
    parse_product_specs_text,
    get_condition_selection_keyboard,
    get_quantity_selection_keyboard,
    get_storage_selection_keyboard
)
from database.db import Database
from database.crud import (
    seed_initial_data, create_product, get_product_by_id,
    update_product, update_product_stock
)

class TestAdminProductFlow(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.test_db_path = Path(__file__).resolve().parent / "test_admin_flow.sqlite"
        if self.test_db_path.exists():
            self.test_db_path.unlink()

        self.db = Database(self.test_db_path)
        import database.crud
        self.orig_db = database.crud.db
        database.crud.db = self.db

        await self.db.init_db()
        await seed_initial_data()

    async def asyncTearDown(self):
        import database.crud
        database.crud.db = self.orig_db
        if self.test_db_path.exists():
            try:
                self.test_db_path.unlink()
            except Exception:
                pass

    def test_parse_product_specs(self):
        text = "256GB Storage, Natural Titanium, 100% Battery, 8GB RAM, 1 Year Apple Warranty"
        specs = parse_product_specs_text(text)

        self.assertEqual(specs.get("storage"), "256GB")
        self.assertEqual(specs.get("color"), "Natural Titanium")
        self.assertEqual(specs.get("battery_health"), "100%")
        self.assertEqual(specs.get("ram"), "8GB RAM")

    def test_keyboards_structure(self):
        cond_kb = get_condition_selection_keyboard()
        cond_texts = [btn.text for row in cond_kb.inline_keyboard for btn in row]
        self.assertTrue(any("Brand New" in t for t in cond_texts))
        self.assertTrue(any("Slightly Used" in t for t in cond_texts) or any("Used" in t for t in cond_texts))
        self.assertTrue(any("Refurbished" in t for t in cond_texts))

        qty_kb = get_quantity_selection_keyboard()
        qty_callbacks = [btn.callback_data for row in qty_kb.inline_keyboard for btn in row]
        self.assertIn("adm_addp_qty_1", qty_callbacks)
        self.assertIn("adm_addp_qty_5", qty_callbacks)
        self.assertIn("adm_addp_qty_10", qty_callbacks)

        stor_kb = get_storage_selection_keyboard()
        stor_callbacks = [btn.callback_data for row in stor_kb.inline_keyboard for btn in row]
        self.assertIn("adm_addp_stor_128GB", stor_callbacks)
        self.assertIn("adm_addp_stor_256GB", stor_callbacks)
        self.assertIn("adm_addp_stor_512GB", stor_callbacks)

    async def test_create_and_manage_product_with_condition_and_stock(self):
        pid = await create_product(
            name="iPhone 15 Pro Max",
            price=135000.0,
            condition="Brand New",
            stock_quantity=5,
            storage="256GB",
            color="Natural Titanium",
            battery_health="100%",
            description="Sealed box with 1 year warranty"
        )
        self.assertIsNotNone(pid)

        prod = await get_product_by_id(pid)
        self.assertEqual(prod["name"], "iPhone 15 Pro Max")
        self.assertEqual(prod["condition"], "Brand New")
        self.assertEqual(prod["stock_quantity"], 5)
        self.assertEqual(prod["storage"], "256GB")
        self.assertEqual(prod["color"], "Natural Titanium")
        self.assertEqual(prod["battery_health"], "100%")
        self.assertEqual(prod["availability"], "Available")

        # Update condition to Used
        await update_product(pid, condition="Slightly Used")
        updated = await get_product_by_id(pid)
        self.assertEqual(updated["condition"], "Slightly Used")

        # Update stock to low stock
        await update_product_stock(pid, 2)
        low_stock_prod = await get_product_by_id(pid)
        self.assertEqual(low_stock_prod["stock_quantity"], 2)
        self.assertEqual(low_stock_prod["availability"], "Low Stock")

        # Update stock to zero (Out of stock)
        await update_product_stock(pid, 0)
        out_prod = await get_product_by_id(pid)
        self.assertEqual(out_prod["stock_quantity"], 0)
        self.assertEqual(out_prod["availability"], "Out of Stock")

if __name__ == "__main__":
    unittest.main()
