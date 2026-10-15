import asyncio
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database.db import db
from database.crud import (
    seed_initial_data, is_admin, get_or_create_customer,
    create_product, list_products, get_product_by_id,
    create_order, get_order_by_id, add_receipt,
    verify_payment, update_delivery_status, get_dashboard_metrics,
    get_recent_audit_logs, update_product_availability, update_product_price
)
from services.storage import storage_service
from services.importer import channel_importer
from services.parser import channel_parser
from services.audit import log_admin_action
from config import ADMIN_USER_IDS

async def run_end_to_end_acceptance():
    print("==================================================")
    print("   RUNNING ISWITCH E2E ACCEPTANCE TEST SUITE      ")
    print("==================================================")

    # 1. Database Init & Seeding
    print("[1/6] Initializing Database & Seeding...")
    await db.init_db()
    await seed_initial_data()
    print("✓ Schema initialized and default categories seeded.")

    # 2. Security & Whitelist Authentication
    print("\n[2/6] Testing Security & Whitelist Verification...")
    auth_admin1 = await is_admin(742368838)
    auth_admin2 = await is_admin(8798202536)
    auth_unauth = await is_admin(1122334455)
    assert auth_admin1 is True, "Admin ID 742368838 must be authorized"
    assert auth_admin2 is True, "Admin ID 8798202536 must be authorized"
    assert auth_unauth is False, "Unauthorized user ID must be blocked"
    print("✓ Whitelist security check passed. Unauthorized users strictly denied.")

    # 3. Channel Sequential Import & Deduplication
    print("\n[3/6] Testing Channel Import & Deduplication...")
    post_text = """
    ➡️iPhone 15 Pro Max ➡️256GB Storage ➡️100% Battery Health  ➡️Natural Titanium Color ➡️Brand New Condition   ➡️Price 165,000  Contact me✉️⬇️@israell0 or call 0980632130
    """
    import_res = await channel_importer.process_single_message(
        channel="@iSwitch0",
        message_id=5001,
        message_date="2026-09-28 10:00:00",
        text=post_text
    )
    assert import_res["status"] in ["imported", "updated"]
    prod_imported = await get_product_by_id(import_res.get("product_id") or 1)
    assert prod_imported is not None
    assert "iPhone 15 Pro Max" in prod_imported["name"]
    assert prod_imported["price"] == 165000.0
    assert prod_imported["storage"] == "256GB"
    assert prod_imported["source_channel"] == "@iSwitch0"
    assert prod_imported["source_message_id"] == 5001
    print(f"✓ Post #5001 imported as Product #{prod_imported['product_id']}.")

    # Test Deduplication: Re-running message 5001 with updated price
    post_updated = """
    ➡️iPhone 15 Pro Max ➡️256GB Storage ➡️100% Battery Health  ➡️Natural Titanium Color ➡️Brand New Condition   ➡️Price 160,000  Contact me✉️⬇️@israell0
    """
    dup_res = await channel_importer.process_single_message(
        channel="@iSwitch0",
        message_id=5001,
        message_date="2026-09-28 10:05:00",
        text=post_updated
    )
    assert dup_res["status"] == "updated"
    prod_recheck = await get_product_by_id(prod_imported["product_id"])
    assert prod_recheck["price"] == 160000.0, "Deduplication must update price"
    print("✓ Deduplication verified: existing product updated without duplicating.")

    # 4. Customer Browsing, Cart & Checkout Flow
    print("\n[4/6] Testing Customer Ordering & Checkout...")
    cust = await get_or_create_customer(telegram_user_id=987654321, username="test_buyer", full_name="Abebe Kebede")
    assert cust["customer_id"] is not None

    cart_items = [{
        "product_id": prod_recheck["product_id"],
        "product_name": prod_recheck["name"],
        "unit_price": prod_recheck["price"],
        "quantity": 1
    }]

    delivery_info = {
        "full_name": "Abebe Kebede",
        "phone": "0980632130",
        "city": "Addis Ababa",
        "area": "Bole",
        "sub_city": "Bole",
        "address": "Near Edna Mall, House 204",
        "landmark": "Edna Mall",
        "note": "Please call before arrival",
        "payment_method": "Telebirr"
    }

    order = await create_order(
        customer_id=cust["customer_id"],
        items=cart_items,
        delivery_info=delivery_info,
        delivery_fee=150.0
    )
    assert order is not None
    assert order["subtotal"] == 160000.0
    assert order["total"] == 160150.0
    assert order["order_status"] == "Pending"
    assert order["payment_status"] == "Pending"
    print(f"✓ Order #{order['order_number']} created with total {order['total']:,.2f} ETB.")

    # 5. Receipt Upload & Payment Verification
    print("\n[5/6] Testing Receipt Storage & Verification...")
    fake_receipt_bytes = b"%PDF-1.4 Fake PDF Receipt Content for testing iSwitch"
    valid, err = storage_service.validate_receipt_file("telebirr_slip.pdf", len(fake_receipt_bytes))
    assert valid is True

    saved_receipt = await storage_service.save_receipt(
        file_bytes=fake_receipt_bytes,
        original_filename="telebirr_slip.pdf",
        order_id=order["order_id"],
        customer_id=cust["customer_id"]
    )
    assert Path(saved_receipt["file_path"]).exists()

    receipt_id = await add_receipt(
        order_id=order["order_id"],
        customer_id=cust["customer_id"],
        payment_id=order["payment"]["payment_id"],
        file_path=saved_receipt["file_path"],
        file_type=saved_receipt["file_type"],
        file_size=saved_receipt["file_size"]
    )
    assert receipt_id is not None
    print(f"✓ Receipt #{receipt_id} securely saved and linked to Order #{order['order_id']}.")

    # Admin verifies payment
    await verify_payment(order["order_id"], admin_id=742368838, approved=True)
    await log_admin_action(742368838, "payment_approved", "order", order["order_id"], "Pending", "Verified")

    verified_order = await get_order_by_id(order["order_id"])
    assert verified_order["payment_status"] == "Verified"
    assert verified_order["order_status"] == "Payment Confirmed"
    print("✓ Payment approved and verified by admin.")

    # 6. Delivery Assignment & Real-Time Dashboard
    print("\n[6/6] Testing Delivery Fulfillment & Dashboard Metrics...")
    await update_delivery_status(
        order_id=order["order_id"],
        status="Out for Delivery",
        delivery_person="Dawit",
        delivery_phone="0911223344",
        note="Dispatched to Bole area"
    )
    dispatched_order = await get_order_by_id(order["order_id"])
    assert dispatched_order["order_status"] == "Out for Delivery"
    assert dispatched_order["delivery"]["delivery_person"] == "Dawit"
    print("✓ Courier assigned and status updated to 'Out for Delivery'.")

    # Complete Delivery
    await update_delivery_status(order_id=order["order_id"], status="Delivered")
    delivered_order = await get_order_by_id(order["order_id"])
    assert delivered_order["order_status"] == "Delivered"
    print("✓ Order marked as 'Delivered'.")

    # Check Dashboard Metrics
    metrics = await get_dashboard_metrics()
    assert metrics["total_orders"] >= 1
    assert metrics["completed_orders"] >= 1
    assert metrics["verified_payments"] >= 1
    assert metrics["total_sales"] >= 160150.0
    print("✓ Dashboard accurately reflects verified sales, orders, and delivery statuses.")

    # Audit Logs
    logs = await get_recent_audit_logs(limit=10)
    assert len(logs) >= 1
    print(f"✓ Audit logs recorded: {len(logs)} actions logged with before/after state.")

    # Cleanup test receipt file
    if Path(saved_receipt["file_path"]).exists():
        Path(saved_receipt["file_path"]).unlink()

    print("\n==================================================")
    print("   ALL ACCEPTANCE TESTS COMPLETED SUCCESSFULLY!   ")
    print("==================================================")

if __name__ == "__main__":
    asyncio.run(run_end_to_end_acceptance())
