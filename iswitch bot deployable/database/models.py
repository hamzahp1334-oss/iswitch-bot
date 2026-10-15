import json
from dataclasses import dataclass
from typing import Optional, List, Dict, Any

DEFAULT_CATEGORIES = [
    {"name": "Phones", "slug": "phones", "icon": "📱", "description": "iPhones, Samsung, and top smartphones", "display_order": 1},
    {"name": "Electronics", "slug": "electronics", "icon": "💻", "description": "Laptops, MacBooks, iPads, and gadgets", "display_order": 2},
    {"name": "Accessories", "slug": "accessories", "icon": "🖥", "description": "AirPods, Apple Watches, Chargers, and cases", "display_order": 3},
    {"name": "New Arrivals", "slug": "new_arrivals", "icon": "🔥", "description": "Recently added inventory", "display_order": 4},
    {"name": "Offers", "slug": "offers", "icon": "🏷", "description": "Special discounts and promotion items", "display_order": 5}
]

DEFAULT_SETTINGS = {
    "store_name": "iSwitch Store",
    "store_description": "Brand New Original & Slightly Used iPhones, Electronics & Accessories",
    "currency": "ETB",
    "delivery_fee": "150",
    "contact_phone": "0980632130",
    "support_username": "israell0",
    "business_address": "Addis Ababa, Ethiopia",
    "order_prefix": "ISW",
    "channel_username": "@iSwitch0",
    "payment_methods": json.dumps([
        {
            "id": "telebirr",
            "name": "Telebirr",
            "account_name": "iSwitch / Israel",
            "account_number": "0980632130",
            "phone": "0980632130",
            "instructions": "Send the exact total via Telebirr and upload the transaction screenshot or receipt."
        },
        {
            "id": "cbe",
            "name": "Commercial Bank of Ethiopia (CBE)",
            "account_name": "iSwitch Store",
            "account_number": "100023456789",
            "phone": "0980632130",
            "instructions": "Transfer via CBE Birr or Mobile Banking and upload the receipt image or PDF."
        },
        {
            "id": "awash",
            "name": "Awash Bank",
            "account_name": "iSwitch Store",
            "account_number": "01320876543200",
            "phone": "0980632130",
            "instructions": "Transfer to Awash Bank account and upload your payment receipt."
        }
    ], ensure_ascii=False)
}

PRODUCT_AVAILABILITIES = ["Available", "Low Stock", "Out of Stock", "Sold", "Hidden"]
PRODUCT_CONDITIONS = ["Brand New", "Slightly Used", "Used", "Refurbished", "Other"]
APPROVAL_STATUSES = ["Draft", "Pending Review", "Published", "Hidden", "Sold"]

ORDER_STATUSES = [
    "Pending",
    "Payment Pending",
    "Payment Confirmed",
    "Preparing",
    "Out for Delivery",
    "Delivered",
    "Cancelled",
    "Refunded"
]

DELIVERY_STATUSES = [
    "Pending",
    "Assigned",
    "Picked Up",
    "Out for Delivery",
    "Delivered",
    "Failed",
    "Returned"
]
