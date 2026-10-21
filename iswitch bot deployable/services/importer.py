import os
import re
import json
import asyncio
import logging
import urllib.request
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable

from config import TELEGRAM_CHANNEL, MEDIA_DIR, BASE_DIR
from database.db import db
from database.crud import (
    get_category_by_slug, get_product_by_source, create_product,
    update_product, add_product_image, record_channel_message,
    get_last_scanned_message_id, set_last_scanned_message_id,
    get_channel_sync_stats, clear_product_images
)
from services.parser import channel_parser, ParsedProduct
from services.storage import storage_service

logger = logging.getLogger("iswitch.importer")

async def fetch_live_channel_photo(channel: str, message_id: int) -> Optional[str]:
    """Dynamically fetches the latest working photo URL from the public Telegram channel embed."""
    try:
        clean_chan = channel.lstrip("@")
        for mid in [message_id, message_id - 1, message_id + 1]:
            embed_url = f"https://t.me/{clean_chan}/{mid}?embed=1"
            req = urllib.request.Request(
                embed_url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                html = resp.read().decode("utf-8")
            photos = re.findall(r"background-image:url\('([^']+)'\)", html)
            valid_photos = [p for p in photos if "cdn" in p or "telesco.pe" in p]
            if valid_photos:
                return valid_photos[0]
    except Exception as e:
        logger.debug(f"Could not live fetch photo for {channel}/{message_id}: {e}")
    return None

class ChannelImporter:
    def __init__(self):
        self.is_running = False
        self.is_paused = False
        self.is_cancelled = False
        
        self.channel_username = TELEGRAM_CHANNEL
        self.current_message_id = 0
        self.current_product_name = ""
        self.total_target_messages = 0
        
        # Stats counters
        self.total_scanned = 0
        self.products_detected = 0
        self.products_imported = 0
        self.products_updated = 0
        self.products_skipped = 0
        self.products_needing_review = 0
        self.images_imported = 0
        self.import_errors = 0
        self.failed_messages = []
        self.status_message = "Idle"
        self._progress_callback: Optional[Callable] = None

    def set_progress_callback(self, cb: Callable):
        self._progress_callback = cb

    def get_progress(self) -> dict:
        return {
            "is_running": self.is_running,
            "is_paused": self.is_paused,
            "is_cancelled": self.is_cancelled,
            "channel": self.channel_username,
            "current_message_id": self.current_message_id,
            "current_product_name": self.current_product_name,
            "total_target": self.total_target_messages,
            "total_scanned": self.total_scanned,
            "products_detected": self.products_detected,
            "products_imported": self.products_imported,
            "products_updated": self.products_updated,
            "products_skipped": self.products_skipped,
            "products_needing_review": self.products_needing_review,
            "images_imported": self.images_imported,
            "import_errors": self.import_errors,
            "status_message": self.status_message,
            "failed_count": len(self.failed_messages)
        }

    def pause(self):
        if self.is_running:
            self.is_paused = True
            self.status_message = "Paused"
            logger.info("Import paused by admin.")

    def resume(self):
        if self.is_running and self.is_paused:
            self.is_paused = False
            self.status_message = "Running"
            logger.info("Import resumed by admin.")

    def cancel(self):
        if self.is_running:
            self.is_cancelled = True
            self.is_running = False
            self.status_message = "Cancelled"
            logger.info("Import cancelled by admin.")

    async def _download_and_save_image(self, url_or_path: str, product_id: int) -> Optional[str]:
        """Downloads an image from URL or copies from local file, returning saved path."""
        try:
            if url_or_path.startswith("http://") or url_or_path.startswith("https://"):
                req = urllib.request.Request(
                    url_or_path,
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
                )
                with urllib.request.urlopen(req, timeout=15) as resp:
                    content = resp.read()
                filename = url_or_path.split("/")[-1].split("?")[0] or "photo.jpg"
                saved_path = await storage_service.save_product_media(content, filename, product_id)
                self.images_imported += 1
                return saved_path
            elif os.path.exists(url_or_path):
                with open(url_or_path, "rb") as f:
                    content = f.read()
                filename = Path(url_or_path).name
                saved_path = await storage_service.save_product_media(content, filename, product_id)
                self.images_imported += 1
                return saved_path
        except Exception as e:
            logger.warning(f"Failed to download/save image from {url_or_path}: {e}")
            return None
        return None

    async def process_single_message(
        self,
        channel: str,
        message_id: int,
        message_date: str,
        text: str,
        media_urls_or_files: list[str] = None,
        source_channel_id: str = None
    ) -> dict:
        """
        Processes one channel message sequentially:
        - Analyze text
        - Determine if valid product
        - Deduplicate (update if exists, insert if new)
        - Save traceability info
        - Never hallucinate missing data
        """
        self.current_message_id = message_id
        self.total_scanned += 1
        clean_channel = channel.lstrip("@")
        post_url = f"https://t.me/{clean_channel}/{message_id}"

        parsed = channel_parser.parse(text)
        if not parsed.is_product:
            self.products_skipped += 1
            await record_channel_message(
                channel=channel,
                message_id=message_id,
                message_date=message_date,
                text=text,
                media_ref=json.dumps(media_urls_or_files) if media_urls_or_files else None,
                is_product=0,
                status="skipped"
            )
            return {"status": "skipped", "message_id": message_id}

        self.products_detected += 1
        self.current_product_name = parsed.name or "Detected Product"

        # Resolve category
        cat = await get_category_by_slug(parsed.category_slug or "phones")
        cat_id = cat["category_id"] if cat else 1

        # Check existing product for deduplication
        existing = await get_product_by_source(channel, message_id)

        if existing:
            # UPDATE existing product
            prod_id = existing["product_id"]
            update_data = {
                "name": parsed.name or existing["name"],
                "category_id": cat_id,
                "brand": parsed.brand or existing["brand"],
                "model": parsed.model or existing["model"],
                "description": parsed.description or existing["description"],
                "price": parsed.price if parsed.price is not None else existing["price"],
                "condition": parsed.condition or existing["condition"],
                "storage": parsed.storage or existing["storage"],
                "ram": parsed.ram or existing["ram"],
                "color": parsed.color or existing["color"],
                "battery_health": parsed.battery_health or existing["battery_health"],
                "availability": parsed.availability or existing["availability"],
                "approval_status": parsed.approval_status or existing["approval_status"],
                "featured": 1 if parsed.is_discounted else existing["featured"],
                "new_arrival": 1 if parsed.new_arrival else existing["new_arrival"],
                "parse_confidence": parsed.confidence
            }
            await update_product(prod_id, **update_data)
            self.products_updated += 1

            # Attach fresh media and clean up any old broken image paths
            if media_urls_or_files:
                cleared_old = False
                for idx, m_url in enumerate(media_urls_or_files):
                    saved_path = await self._download_and_save_image(m_url, prod_id)
                    if saved_path:
                        if not cleared_old:
                            await clear_product_images(prod_id)
                            cleared_old = True
                        await add_product_image(
                            product_id=prod_id,
                            file_path=saved_path,
                            is_primary=1 if idx == 0 else 0,
                            file_url=m_url if m_url.startswith("http") else None
                        )

            await record_channel_message(
                channel=channel,
                message_id=message_id,
                message_date=message_date,
                text=text,
                media_ref=json.dumps(media_urls_or_files) if media_urls_or_files else None,
                is_product=1,
                product_id=prod_id,
                status="updated"
            )
            return {"status": "updated", "product_id": prod_id, "name": parsed.name}

        else:
            # CREATE new product
            approval_status = parsed.approval_status
            if approval_status == "Pending Review":
                self.products_needing_review += 1
            else:
                self.products_imported += 1

            prod_id = await create_product(
                name=parsed.name or f"Channel Item #{message_id}",
                category_id=cat_id,
                brand=parsed.brand,
                model=parsed.model,
                description=parsed.description,
                price=parsed.price,
                currency="ETB",
                condition=parsed.condition,
                storage=parsed.storage,
                ram=parsed.ram,
                color=parsed.color,
                battery_health=parsed.battery_health,
                stock_quantity=1,
                availability=parsed.availability,
                approval_status=approval_status,
                featured=1 if parsed.is_discounted else 0,
                new_arrival=1 if parsed.new_arrival else 0,
                source_channel=channel,
                source_channel_id=source_channel_id,
                source_message_id=message_id,
                source_message_url=post_url,
                source_message_date=message_date,
                parse_confidence=parsed.confidence
            )

            # Attach media
            if media_urls_or_files:
                for idx, m_url in enumerate(media_urls_or_files):
                    saved_path = await self._download_and_save_image(m_url, prod_id)
                    if saved_path:
                        await add_product_image(
                            product_id=prod_id,
                            file_path=saved_path,
                            is_primary=1 if idx == 0 else 0,
                            file_url=m_url if m_url.startswith("http") else None
                        )

            await record_channel_message(
                channel=channel,
                message_id=message_id,
                message_date=message_date,
                text=text,
                media_ref=json.dumps(media_urls_or_files) if media_urls_or_files else None,
                is_product=1,
                product_id=prod_id,
                status="needs_review" if approval_status == "Pending Review" else "imported"
            )
            return {"status": "imported", "product_id": prod_id, "name": parsed.name}

    async def import_from_json_export(self, export_file_path: Path | str) -> dict:
        """Method A: Imports channel messages from a Telegram Desktop JSON export file."""
        export_path = Path(export_file_path)
        if not export_path.exists():
            return {"success": False, "error": f"File {export_file_path} does not exist."}

        self.is_running = True
        self.is_paused = False
        self.is_cancelled = False
        self.status_message = "Importing from JSON export..."

        try:
            with open(export_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            messages = data.get("messages", [])
            self.total_target_messages = len(messages)
            logger.info(f"Loaded {len(messages)} messages from JSON export {export_path.name}")

            for msg in messages:
                while self.is_paused:
                    await asyncio.sleep(1)
                if self.is_cancelled:
                    break

                # Extract text
                msg_text = ""
                raw_text = msg.get("text", "")
                if isinstance(raw_text, str):
                    msg_text = raw_text
                elif isinstance(raw_text, list):
                    parts = []
                    for p in raw_text:
                        parts.append(p if isinstance(p, str) else p.get("text", ""))
                    msg_text = "".join(parts)

                msg_id = msg.get("id")
                msg_date = msg.get("date", datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))

                # Media paths
                media_files = []
                if "photo" in msg and msg["photo"]:
                    photo_subpath = msg["photo"]
                    full_photo_path = export_path.parent / photo_subpath
                    if full_photo_path.exists():
                        media_files.append(str(full_photo_path))

                try:
                    await self.process_single_message(
                        channel=self.channel_username,
                        message_id=msg_id,
                        message_date=msg_date,
                        text=msg_text,
                        media_urls_or_files=media_files
                    )
                    await set_last_scanned_message_id(self.channel_username, msg_id)
                except Exception as ex:
                    logger.error(f"Error processing message {msg_id}: {ex}")
                    self.import_errors += 1
                    self.failed_messages.append({"message_id": msg_id, "error": str(ex), "text": msg_text})

                if self._progress_callback:
                    await self._progress_callback(self.get_progress())

                await asyncio.sleep(0.01)

            self.status_message = "Completed" if not self.is_cancelled else "Cancelled"
            return {"success": True, "progress": self.get_progress()}

        except Exception as e:
            logger.error(f"Failed JSON export import: {e}", exc_info=True)
            self.status_message = f"Error: {e}"
            return {"success": False, "error": str(e)}
        finally:
            self.is_running = False

    async def import_from_web_pagination(self, max_pages: int = 15, delay_seconds: float = 1.0) -> dict:
        """
        Public channel web pagination sync:
        Walks backward through t.me/s/iSwitch0 messages until exhausted or limit reached.
        """
        self.is_running = True
        self.is_paused = False
        self.is_cancelled = False
        self.status_message = "Synchronizing via Channel Web Pagination..."

        clean_channel = self.channel_username.lstrip("@")
        current_before = None

        try:
            for page in range(max_pages):
                while self.is_paused:
                    await asyncio.sleep(1)
                if self.is_cancelled:
                    break

                url = f"https://t.me/s/{clean_channel}"
                if current_before:
                    url += f"?before={current_before}"

                logger.info(f"Scanning web batch: {url}")
                req = urllib.request.Request(
                    url,
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
                )

                try:
                    with urllib.request.urlopen(req, timeout=15) as resp:
                        html_content = resp.read().decode("utf-8")
                except Exception as net_err:
                    logger.warning(f"Network error accessing {url}: {net_err}")
                    self.import_errors += 1
                    break

                # Extract messages blocks: post id, text, and photos
                # Match widget blocks
                message_matches = re.findall(
                    r'data-post="[^\"]+/(\d+)".*?<div class="tgme_widget_message_text[^>]*>(.*?)</div>',
                    html_content,
                    re.DOTALL
                )

                if not message_matches:
                    logger.info("No more messages found in web preview.")
                    break

                # Process batch messages
                min_id_in_batch = None
                for msg_id_str, text_html in message_matches:
                    while self.is_paused:
                        await asyncio.sleep(1)
                    if self.is_cancelled:
                        break

                    msg_id = int(msg_id_str)
                    min_id_in_batch = min(min_id_in_batch or msg_id, msg_id)

                    # Extract photos for this specific message id if present
                    # Find snippet around this message
                    msg_block_pattern = rf'data-post="[^\"]+/{msg_id}".*?(?=data-post=|$)'
                    block_match = re.search(msg_block_pattern, html_content, re.DOTALL)
                    photo_urls = []
                    if block_match:
                        block_text = block_match.group(0)
                        # Extract background-image:url('...')
                        photos = re.findall(r"background-image:url\('([^']+)'\)", block_text)
                        photo_urls = [p for p in photos if "cdn" in p or "telesco.pe" in p]

                    # If no photos found in message block, check adjacent album posts
                    if not photo_urls:
                        for n_id in [msg_id - 1, msg_id + 1]:
                            n_pattern = rf'data-post="[^\"]+/{n_id}".*?(?=data-post=|$)'
                            n_match = re.search(n_pattern, html_content, re.DOTALL)
                            if n_match:
                                n_photos = re.findall(r"background-image:url\('([^']+)'\)", n_match.group(0))
                                valid_n = [p for p in n_photos if "cdn" in p or "telesco.pe" in p]
                                if valid_n:
                                    photo_urls = valid_n
                                    break

                    # Parse and save
                    now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
                    try:
                        await self.process_single_message(
                            channel=self.channel_username,
                            message_id=msg_id,
                            message_date=now_str,
                            text=text_html,
                            media_urls_or_files=photo_urls
                        )
                        await set_last_scanned_message_id(self.channel_username, msg_id)
                    except Exception as ex:
                        logger.error(f"Error on message {msg_id}: {ex}")
                        self.import_errors += 1
                        self.failed_messages.append({"message_id": msg_id, "error": str(ex), "text": text_html})

                    if self._progress_callback:
                        await self._progress_callback(self.get_progress())

                if min_id_in_batch and (not current_before or min_id_in_batch < current_before):
                    current_before = min_id_in_batch
                else:
                    break

                await asyncio.sleep(delay_seconds)

            self.status_message = "Completed" if not self.is_cancelled else "Cancelled"
            return {"success": True, "progress": self.get_progress()}

        except Exception as e:
            logger.error(f"Web sync error: {e}", exc_info=True)
            self.status_message = f"Error: {e}"
            return {"success": False, "error": str(e)}
        finally:
            self.is_running = False

    async def import_from_telethon(
        self,
        api_id: int | str,
        api_hash: str,
        session_string: str = None,
        limit: int = None
    ) -> dict:
        """
        Method B: Authorized MTProto integration using Telethon.
        Requires channel owner/admin to provide valid API ID and API HASH.
        """
        try:
            from telethon import TelegramClient
            from telethon.tl.types import MessageMediaPhoto
        except ImportError:
            return {"success": False, "error": "Telethon library is not installed."}

        self.is_running = True
        self.is_paused = False
        self.is_cancelled = False
        self.status_message = "Connecting to Telegram MTProto API..."

        try:
            client = TelegramClient(
                session_string or "iswitch_session",
                int(api_id),
                api_hash
            )
            await client.connect()
            if not await client.is_user_authorized():
                await client.disconnect()
                return {
                    "success": False,
                    "error": "Client session is not authorized. Admin must provide authorized session string or complete login."
                }

            self.status_message = f"Paginating channel history for {self.channel_username}..."
            entity = await client.get_entity(self.channel_username)

            async for msg in client.iter_messages(entity, reverse=True, limit=limit):
                while self.is_paused:
                    await asyncio.sleep(1)
                if self.is_cancelled:
                    break

                msg_id = msg.id
                msg_text = msg.message or ""
                msg_date = msg.date.strftime("%Y-%m-%d %H:%M:%S") if msg.date else ""

                media_paths = []
                if msg.photo:
                    dest = MEDIA_DIR / f"tg_{msg_id}.jpg"
                    await client.download_media(msg.photo, file=str(dest))
                    if dest.exists():
                        media_paths.append(str(dest))

                try:
                    await self.process_single_message(
                        channel=self.channel_username,
                        message_id=msg_id,
                        message_date=msg_date,
                        text=msg_text,
                        media_urls_or_files=media_paths
                    )
                    await set_last_scanned_message_id(self.channel_username, msg_id)
                except Exception as ex:
                    logger.error(f"MTProto message {msg_id} error: {ex}")
                    self.import_errors += 1
                    self.failed_messages.append({"message_id": msg_id, "error": str(ex), "text": msg_text})

                if self._progress_callback:
                    await self._progress_callback(self.get_progress())

            await client.disconnect()
            self.status_message = "Completed" if not self.is_cancelled else "Cancelled"
            return {"success": True, "progress": self.get_progress()}

        except Exception as e:
            logger.error(f"Telethon import failure: {e}", exc_info=True)
            self.status_message = f"Error: {e}"
            return {"success": False, "error": str(e)}
        finally:
            self.is_running = False

# Global importer instance
channel_importer = ChannelImporter()
