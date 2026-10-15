import re
import html
from dataclasses import dataclass
from typing import Optional, List, Dict, Any

@dataclass
class ParsedProduct:
    is_product: bool
    name: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    category_slug: Optional[str] = None
    price: Optional[float] = None
    currency: str = "ETB"
    condition: Optional[str] = None
    storage: Optional[str] = None
    ram: Optional[str] = None
    color: Optional[str] = None
    battery_health: Optional[str] = None
    availability: str = "Available"
    approval_status: str = "Published"
    confidence: float = 0.0
    contacts: List[str] = None
    telegram_username: Optional[str] = None
    description: str = ""
    is_discounted: bool = False
    new_arrival: bool = False

class ChannelParser:
    def __init__(self):
        # Known Brands
        self.brands = [
            "Apple", "iPhone", "Samsung", "Google Pixel", "Xiaomi", "Redmi",
            "OnePlus", "Huawei", "Sony", "Dell", "HP", "Lenovo", "Asus", "Acer", "MacBook", "iPad"
        ]

        # Common non-product keywords in Ethiopian channels
        self.skip_patterns = [
            r"^\s*Welcome to",
            r"Our services:?-?",
            r"Join our channel",
            r"Sponsored",
            r"Giveaway",
            r"Eid Mubarak",
            r"Merry Christmas",
            r"Happy New Year",
            r"መልካም አዲስ አመት",
            r"እንኳን አደረሳችሁ"
        ]

    def clean_text(self, raw_text: str) -> str:
        if not raw_text:
            return ""
        # Unescape HTML
        text = html.unescape(raw_text)
        # Normalize newlines
        text = re.sub(r'<br\s*/?>', '\n', text)
        text = re.sub(r'<[^>]+>', ' ', text)
        return text.strip()

    def is_likely_non_product(self, text: str) -> bool:
        if len(text.strip()) < 15:
            return True
        for pat in self.skip_patterns:
            if re.search(pat, text, re.IGNORECASE):
                # If it's a general announcement without price, skip
                if not re.search(r'(?:Price|ዋጋ|ETB|Birr|ብር)\s*[:\-\s]*[\d,]+', text, re.IGNORECASE):
                    return True
        return False

    def parse(self, raw_text: str) -> ParsedProduct:
        text = self.clean_text(raw_text)
        if not text or self.is_likely_non_product(text):
            return ParsedProduct(is_product=False, description=text)

        lines = [line.strip() for line in text.split("\n") if line.strip()]
        if not lines:
            return ParsedProduct(is_product=False, description=text)

        # 1. Price Extraction
        price = None
        price_match = re.search(
            r'(?:Price|ዋጋ|ዋጋው|ዋጋ፡)\s*[:\-\s🔥💥🛍]*([0-9]{1,3}(?:,[0-9]{3})*|[0-9]{3,7})\b',
            text,
            re.IGNORECASE
        )
        if not price_match:
            # Try alternate pattern: 13,500 ETB / Birr / ብር
            price_match = re.search(r'\b([0-9]{1,3}(?:,[0-9]{3})*|[0-9]{4,7})\s*(?:ETB|Birr|ብር)\b', text, re.IGNORECASE)

        if price_match:
            try:
                cleaned_price_str = price_match.group(1).replace(",", "").strip()
                price = float(cleaned_price_str)
            except ValueError:
                price = None

        # 2. Extract Title / Name
        # Usually the first line or line after decorative emojis
        name = None
        for line in lines:
            cleaned_line = re.sub(r'^[➡️▪️•⭐️🛍🔥*#\s]+|[⭐️🛍🔥*#\s]+$', '', line).strip()
            # Skip holiday headers like "Holiday Discounted"
            cleaned_line = re.sub(r'^(?:Holiday Discounted|Special Offer|Discounted)\s*', '', cleaned_line, flags=re.IGNORECASE).strip()
            if any(k in cleaned_line.lower() for k in ["iphone", "samsung", "airpod", "watch", "macbook", "ipad", "pixel", "galaxy"]):
                name = cleaned_line
                break
            elif len(cleaned_line) > 3 and not re.search(r'^(?:Storage|RAM|Price|Battery|Color|Contact|Call)\b', cleaned_line, re.IGNORECASE):
                if not name:
                    name = cleaned_line

        if not name and lines:
            # Fallback to first line
            name = re.sub(r'^[➡️▪️•⭐️🛍🔥*#\s]+|[⭐️🛍🔥*#\s]+$', '', lines[0]).strip()

        # 3. Brand
        brand = None
        if name:
            for b in self.brands:
                if re.search(rf'\b{b}\b', name, re.IGNORECASE):
                    brand = "Apple" if b in ["iPhone", "MacBook", "iPad"] else b
                    break
        if not brand and text:
            for b in self.brands:
                if re.search(rf'\b{b}\b', text, re.IGNORECASE):
                    brand = "Apple" if b in ["iPhone", "MacBook", "iPad"] else b
                    break

        # 4. Storage
        storage = None
        storage_match = re.search(r'\b(\d+\s*(?:GB|TB))\s*(?:Storage|ስቶሬጅ|ማከማቻ)?\b', text, re.IGNORECASE)
        if storage_match:
            storage = storage_match.group(1).replace(" ", "").upper()

        # 5. RAM
        ram = None
        ram_match = re.search(r'\b(\d+\s*GB)\s*(?:RAM|ራም)\b', text, re.IGNORECASE)
        if ram_match:
            ram = ram_match.group(1).replace(" ", "").upper()

        # 6. Battery Health
        battery_health = None
        battery_match = re.search(r'(?:Battery\s*Health|Battery|ባትሪ|ባትሪ\s*ጤንነት)\s*[:\-\s]*(\d{1,3}%?)\b', text, re.IGNORECASE)
        if not battery_match:
            battery_match = re.search(r'\b(\d{1,3}%)\s*(?:Battery\s*Health|Battery)\b', text, re.IGNORECASE)
        if battery_match:
            val = battery_match.group(1)
            battery_health = val if val.endswith("%") else f"{val}%"
        elif re.search(r'Good Battery Life', text, re.IGNORECASE):
            battery_health = "Good Battery Life"

        # 7. Color
        color = None
        color_match = re.search(r'([A-Za-z\s]+?)\s*(?:Color|ቀለም|ከለር)\b', text, re.IGNORECASE)
        if color_match:
            c = color_match.group(1).strip()
            # Clean common prefixes like "➡️"
            c = re.sub(r'^[➡️▪️•\s]+', '', c)
            if len(c) < 25 and not any(w in c.lower() for w in ["works", "battery", "storage", "sim"]):
                color = c

        # 8. Condition
        condition = None
        if re.search(r'\b(?:Brand New|አዲስ|ድንግል)\b', text, re.IGNORECASE):
            condition = "Brand New"
        elif re.search(r'\b(?:Slightly Used|Almost New|Clean|Clean Condition|ንጹህ|በጥቂቱ የተሠራበት|እንደ አዲስ)\b', text, re.IGNORECASE):
            condition = "Slightly Used"
        elif re.search(r'\b(?:Refurbished|የታደሰ)\b', text, re.IGNORECASE):
            condition = "Refurbished"
        elif re.search(r'\b(?:Used|ያገለገለ)\b', text, re.IGNORECASE):
            condition = "Used"

        # 9. Availability
        availability = "Available"
        if re.search(r'\b(?:Sold Out|Sold|ተሽጧል)\b', text, re.IGNORECASE):
            availability = "Sold"
        elif re.search(r'\b(?:Out of Stock)\b', text, re.IGNORECASE):
            availability = "Out of Stock"

        # 10. Category
        category_slug = "phones"
        target_corpus = f"{name or ''} {text}".lower()
        if any(w in target_corpus for w in ["airpod", "watch", "charger", "case", "cable", "adapter", "earbuds", "headphone"]):
            category_slug = "accessories"
        elif any(w in target_corpus for w in ["macbook", "ipad", "laptop", "tablet", "computer", "pc", "monitor"]):
            category_slug = "electronics"
        elif any(w in target_corpus for w in ["iphone", "samsung", "galaxy", "phone", "pixel", "redmi", "xiaomi"]):
            category_slug = "phones"

        # 11. Discounts & New Arrivals
        is_discounted = bool(re.search(r'\b(?:Discount|Discounted|Holiday Discounted|ቀናሽ|ቅናሽ)\b', text, re.IGNORECASE))
        new_arrival = bool(re.search(r'\b(?:New Arrival|New Arrivals|አዲስ ገቢ)\b', text, re.IGNORECASE) or condition == "Brand New")

        # 12. Contacts & Telegram
        contacts = re.findall(r'\b(?:09\d{8}|07\d{8}|\+251\d{9})\b', text)
        tg_match = re.search(r'@([A-Za-z0-9_]{4,32})', text)
        telegram_username = tg_match.group(1) if tg_match else "israell0"

        # 13. Confidence & Approval
        confidence = 0.0
        if name:
            confidence += 0.35
        if price:
            confidence += 0.35
        if storage or ram or battery_health:
            confidence += 0.20
        if condition:
            confidence += 0.10

        # Non-hallucination rule:
        # If confidence is low or crucial fields missing -> flag for review
        approval_status = "Published" if (confidence >= 0.70 and price is not None and name is not None) else "Pending Review"

        return ParsedProduct(
            is_product=True,
            name=name,
            brand=brand,
            model=name,
            category_slug=category_slug,
            price=price,
            currency="ETB",
            condition=condition,
            storage=storage,
            ram=ram,
            color=color,
            battery_health=battery_health,
            availability=availability,
            approval_status=approval_status,
            confidence=round(confidence, 2),
            contacts=list(set(contacts)),
            telegram_username=telegram_username,
            description=text,
            is_discounted=is_discounted,
            new_arrival=new_arrival
        )

# Global parser instance
channel_parser = ChannelParser()
