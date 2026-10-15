import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database.db import Database
from database.crud import seed_initial_data, get_product_by_source, list_products
from services.importer import channel_importer

test_imp_db_path = Path(__file__).resolve().parent / "test_imp_db.sqlite"
test_imp_db = Database(test_imp_db_path)

async def test_importer_flow():
    print("Testing Channel Importer...")
    if test_imp_db_path.exists():
        test_imp_db_path.unlink()

    import database.crud
    database.crud.db = test_imp_db
    await test_imp_db.init_db()
    await seed_initial_data()

    # Message 1: iPhone XS
    msg1_text = """
    ➡️iPhone XS ➡️64GB Storage ➡️100% Battery Health  ➡️Silver Color ➡️Everything Works Perfectly Fine  ➡️Slightly Used Condition   ➡️Price 22,000  Contact me✉️⬇️@israell0 or call 0980632130 , 0709632130
    """
    res1 = await channel_importer.process_single_message(
        channel="@iSwitch0",
        message_id=2930,
        message_date="2026-09-20 12:00:00",
        text=msg1_text
    )
    assert res1["status"] in ["imported", "needs_review"]
    p1 = await get_product_by_source("@iSwitch0", 2930)
    assert p1 is not None
    assert "iPhone XS" in p1["name"]
    assert p1["price"] == 22000.0
    assert p1["storage"] == "64GB"
    print(f"✓ Message 2930 imported successfully as product ID {p1['product_id']}.")

    # Test Deduplication: Same message ID processed again with an updated price
    msg1_updated_text = """
    ➡️iPhone XS ➡️64GB Storage ➡️100% Battery Health  ➡️Silver Color ➡️Slightly Used Condition   ➡️Price 21,500  Contact me✉️⬇️@israell0
    """
    res1_dup = await channel_importer.process_single_message(
        channel="@iSwitch0",
        message_id=2930,
        message_date="2026-09-20 12:05:00",
        text=msg1_updated_text
    )
    assert res1_dup["status"] == "updated"
    p1_updated = await get_product_by_source("@iSwitch0", 2930)
    assert p1_updated["product_id"] == p1["product_id"], "Product ID must not change upon re-import"
    assert p1_updated["price"] == 21500.0, "Product price should be updated"
    print("✓ Deduplication verified: existing product updated without creating duplicates.")

    # Message 2: Non-product announcement -> Should be skipped
    msg2_text = "Welcome to iSwitch! Call 0980632130 for inquiries."
    res2 = await channel_importer.process_single_message(
        channel="@iSwitch0",
        message_id=2931,
        message_date="2026-09-20 12:10:00",
        text=msg2_text
    )
    assert res2["status"] == "skipped"
    print("✓ Non-product message skipped.")

    # Message 3: Incomplete product without price -> Should go to review queue / pending review
    msg3_text = "➡️Samsung Galaxy S22 Ultra 256GB Storage. Clean condition. Contact @israell0"
    res3 = await channel_importer.process_single_message(
        channel="@iSwitch0",
        message_id=2932,
        message_date="2026-09-20 12:15:00",
        text=msg3_text
    )
    p3 = await get_product_by_source("@iSwitch0", 2932)
    assert p3 is not None
    assert p3["approval_status"] == "Pending Review", "Incomplete product without price must be Pending Review"
    print("✓ Non-hallucination verified: item without price placed into Pending Review.")

    # Test Telegram Desktop Export simulation
    sample_export = {
        "name": "iSwitch",
        "type": "public_channel",
        "id": 12345678,
        "messages": [
            {
                "id": 3001,
                "type": "message",
                "date": "2026-09-21T10:00:00",
                "text": "➡️iPhone 14 128GB Storage ➡️88% Battery ➡️Clean Condition ➡️Price 38,000 Contact @israell0"
            },
            {
                "id": 3002,
                "type": "message",
                "date": "2026-09-21T10:05:00",
                "text": "Happy Sunday to everyone!"
            }
        ]
    }
    tmp_export_file = Path(__file__).resolve().parent / "temp_export.json"
    with open(tmp_export_file, "w", encoding="utf-8") as f:
        json.dump(sample_export, f)

    export_res = await channel_importer.import_from_json_export(tmp_export_file)
    assert export_res["success"] is True
    assert channel_importer.products_imported >= 1
    p_exp = await get_product_by_source("@iSwitch0", 3001)
    assert p_exp is not None
    assert p_exp["price"] == 38000.0
    print("✓ Telegram JSON export importer verified.")

    if tmp_export_file.exists():
        tmp_export_file.unlink()

    if test_imp_db_path.exists():
        test_imp_db_path.unlink()

    print("\nALL IMPORTER TESTS PASSED!")

if __name__ == "__main__":
    asyncio.run(test_importer_flow())
