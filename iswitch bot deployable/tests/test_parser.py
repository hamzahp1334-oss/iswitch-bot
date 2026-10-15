import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.parser import channel_parser

def test_parser_samples():
    sample1 = """
    ➡️iPhone XS ➡️64GB Storage ➡️100% Battery Health  ➡️Silver Color ➡️Everything Works Perfectly Fine  ➡️Slightly Used Condition   ➡️Price 22,000  Contact me✉️⬇️@israell0 or call 0980632130 , 0709632130 for more iPhones to buy , sell & exchanges
    """
    res1 = channel_parser.parse(sample1)
    assert res1.is_product is True
    assert "iPhone XS" in res1.name
    assert res1.storage == "64GB"
    assert res1.battery_health == "100%"
    assert res1.color == "Silver"
    assert res1.price == 22000.0
    assert res1.condition == "Slightly Used"
    assert res1.category_slug == "phones"
    print("✓ Sample 1 (iPhone XS) parsed correctly.")

    sample2 = """
    ⭐️➡️Holiday Discounted🛍 Samsung S25 Ultra⭐️
    ➡️256GB Storage
    ➡️12GB RAM
    ➡️Dual Sim
    ➡️Clean✨

    ➡️Price 🔥130,000💥

    Contact me @✉️⬇️israell0 or call 0980632130 , 0709632130 for more Phones to buy , sell & exchanges
    """
    res2 = channel_parser.parse(sample2)
    assert res2.is_product is True
    assert "Samsung S25 Ultra" in res2.name
    assert res2.storage == "256GB"
    assert res2.ram == "12GB"
    assert res2.price == 130000.0
    assert res2.brand == "Samsung"
    assert res2.is_discounted is True
    print("✓ Sample 2 (Samsung S25 Ultra with discount) parsed correctly.")

    sample3 = """
    ➡️AirPod Pro 1st Generation 
    ➡️Genuine Apple Product💯
    ➡️Slightly Used Condition 
    ➡️Good Battery Life⚡️

    ➡️Price 12,000

    Contact me✉️⬇️@israell0 or call 0980632130 , 0709632130 for more items to buy , sell & exchanges
    """
    res3 = channel_parser.parse(sample3)
    assert res3.is_product is True
    assert "AirPod" in res3.name
    assert res3.price == 12000.0
    assert res3.category_slug == "accessories"
    assert res3.condition == "Slightly Used"
    print("✓ Sample 3 (AirPod Pro) parsed correctly.")

    sample4 = """
    ➡️Apple Watch Series 6
    ➡️88% Battery Health 
    ➡️44MM Size 
    ➡️Clean

    ➡️Price 21,000

    Contact  me ✉️⬇️ @israell0 or call 0980632130 , 0709632130 for more iPhones to buy , sell & exchanges
    """
    res4 = channel_parser.parse(sample4)
    assert res4.is_product is True
    assert "Apple Watch" in res4.name
    assert res4.price == 21000.0
    assert res4.category_slug == "accessories"
    assert res4.battery_health == "88%"
    print("✓ Sample 4 (Apple Watch Series 6) parsed correctly.")

    # Non-product greeting
    sample_greeting = """
    Welcome to iSwitch!
    Call 0980632130 for more info.
    Happy New Year to all our valued customers!
    """
    res_greet = channel_parser.parse(sample_greeting)
    assert res_greet.is_product is False
    print("✓ Non-product announcement successfully skipped.")

    # Mixed Amharic sample
    sample_amharic = """
    iPhone 13 128GB
    ባትሪ ጤንነት 89%
    ንጹህ ስልክ
    ዋጋ 55,000 ብር
    ይደውሉ 0980632130
    """
    res_amh = channel_parser.parse(sample_amharic)
    assert res_amh.is_product is True
    assert res_amh.price == 55000.0
    assert res_amh.storage == "128GB"
    assert res_amh.condition == "Slightly Used"
    print("✓ Mixed Amharic post parsed correctly.")

    print("\nALL PARSER TESTS PASSED!")

if __name__ == "__main__":
    test_parser_samples()
