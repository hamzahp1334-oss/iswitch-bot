import asyncio
import os
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database.db import Database
from database.crud import (
    seed_initial_data, is_admin, get_all_categories, create_product,
    list_products, create_order, get_order_by_id, verify_payment,
    get_dashboard_metrics, log_audit_action, get_recent_audit_logs,
    get_or_create_customer, add_product_image, get_product_images
)

test_db_path = Path(__file__).resolve().parent / "test_db.sqlite"
test_db_instance = Database(test_db_path)

async def test_db():
    print("Testing DB initialization...")
    if test_db_path.exists():
        test_db_path.unlink()

    # Re-route db to test db
    import database.crud
    database.crud.db = test_db_instance
    await test_db_instance.init_db()
    await seed_initial_data()

    # Check Admins
    admin_auth1 = await is_admin(742368838)
    admin_auth2 = await is_admin(8798202536)
    admin_auth3 = await is_admin(999999999) # should be False
    assert admin_auth1 is True, "Admin 1 should be authorized"
    assert admin_auth2 is True, "Admin 2 should be authorized"
    assert admin_auth3 is False, "Random user should NOT be authorized"
    print("✓ Admin authorization whitelist verified.")

    # Check Categories
    cats = await get_all_categories()
    assert len(cats) >= 5, f"Expected at least 5 categories, got {len(cats)}"
    print(f"✓ Categories loaded: {[c['name'] for c in cats]}")

    # Create Customer
    cust = await get_or_create_customer(12345678, "testuser", "Test Customer")
    assert cust["customer_id"] is not None
    print("✓ Customer created.")

    # Create Product
    pid = await create_product(
        name="iPhone 15 Pro",
        category_id=cats[0]["category_id"],
        brand="Apple",
        model="15 Pro",
        description="Titanium, Natural Titanium, 100% Battery",
        price=145000.0,
        currency="ETB",
        condition="Brand New",
        storage="256GB",
        ram="8GB",
        color="Natural Titanium",
        battery_health="100%",
        stock_quantity=5,
        availability="Available",
        approval_status="Published"
    )
    assert pid is not None
    print(f"✓ Product created with ID {pid}.")

    # Add Product Image Test
    img_id = await add_product_image(
        product_id=pid,
        file_path="data/media/test_sample.jpg",
        is_primary=1,
        telegram_file_id="AgACAgQAAxkBAAE12345"
    )
    assert img_id is not None
    imgs = await get_product_images(pid)
    assert len(imgs) == 1
    assert imgs[0]["telegram_file_id"] == "AgACAgQAAxkBAAE12345"
    print(f"✓ Product image added and retrieved successfully (img_id={img_id}).")

    # List Products
    prods, total = await list_products(category_id=cats[0]["category_id"])
    assert total >= 1
    assert prods[0]["name"] == "iPhone 15 Pro"
    print(f"✓ Product listed successfully: total={total}")

    # Create Order
    items = [{"product_id": pid, "product_name": "iPhone 15 Pro", "unit_price": 145000.0, "quantity": 1}]
    deliv_info = {
        "full_name": "Test Customer",
        "phone": "0911223344",
        "city": "Addis Ababa",
        "area": "Bole",
        "sub_city": "Bole",
        "address": "Around Edna Mall",
        "landmark": "Near Edna Mall",
        "note": "Call when arrived"
    }
    order = await create_order(cust["customer_id"], items, deliv_info, delivery_fee=150.0)
    assert order["order_id"] is not None
    assert order["total"] == 145150.0
    print(f"✓ Order created: {order['order_number']}, total: {order['total']} ETB")

    # Verify Payment
    await verify_payment(order["order_id"], admin_id=742368838, approved=True)
    updated_order = await get_order_by_id(order["order_id"])
    assert updated_order["payment_status"] == "Verified"
    assert updated_order["order_status"] == "Payment Confirmed"
    print("✓ Payment verified and order status transitioned.")

    # Audit Log
    await log_audit_action(
        admin_id=742368838,
        action="payment_approved",
        target_type="order",
        target_id=str(order["order_id"]),
        prev_val="Pending",
        new_val="Verified",
        details="Receipt matched Telebirr transaction"
    )
    logs = await get_recent_audit_logs(limit=5)
    assert len(logs) >= 1
    print(f"✓ Audit log recorded: {logs[0]['action']} on target {logs[0]['target_id']}")

    # Dashboard Metrics
    metrics = await get_dashboard_metrics()
    assert metrics["total_products"] >= 1
    assert metrics["total_orders"] >= 1
    assert metrics["verified_payments"] >= 1
    assert metrics["total_sales"] >= 145150.0
    print("✓ Dashboard metrics returned real DB data:")
    print(f"  Products: {metrics['total_products']}, Orders: {metrics['total_orders']}, Total Sales: {metrics['total_sales']} ETB")

    if test_db_path.exists():
        test_db_path.unlink()

    print("\nALL DATABASE TESTS PASSED!")

if __name__ == "__main__":
    asyncio.run(test_db())
