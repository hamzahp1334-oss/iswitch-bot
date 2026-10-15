import sys
import hmac
import logging
from pathlib import Path
from aiohttp import web
from telegram import Update

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from config import (
    CUSTOMER_BOT_TOKEN, ADMIN_BOT_TOKEN, WEBHOOK_PORT, WEBHOOK_SECRET,
    WEBHOOK_URL, TELEGRAM_CHANNEL
)
from database.db import db
from database.crud import seed_initial_data
from services.notifier import notifier
from customer_bot.bot import create_customer_bot_app
from admin_bot.bot import create_admin_bot_app

logging.basicConfig(level=logging.INFO, format="%(asctime)s - [%(name)s] - %(levelname)s - %(message)s")
logger = logging.getLogger("iswitch.webhook")

async def customer_webhook(request: web.Request) -> web.Response:
    app = request.app.get("customer_app")
    if not app:
        return web.Response(status=503, text="Service Unavailable")

    # Security: Strictly verify secret token using constant-time comparison
    secret_token = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not WEBHOOK_SECRET or not secret_token or not hmac.compare_digest(secret_token, WEBHOOK_SECRET):
        return web.Response(status=403, text="Forbidden: Secret verification failed")

    try:
        data = await request.json()
    except Exception:
        return web.Response(status=400, text="Bad Request: Invalid JSON")

    try:
        update = Update.de_json(data, app.bot)
        if update:
            await app.process_update(update)
    except Exception as e:
        logger.error(f"Error processing customer update: {e}", exc_info=True)

    return web.Response(text="OK")

async def admin_webhook(request: web.Request) -> web.Response:
    app = request.app.get("admin_app")
    if not app:
        return web.Response(status=503, text="Service Unavailable")

    # Security: Strictly verify secret token using constant-time comparison
    secret_token = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not WEBHOOK_SECRET or not secret_token or not hmac.compare_digest(secret_token, WEBHOOK_SECRET):
        return web.Response(status=403, text="Forbidden: Secret verification failed")

    try:
        data = await request.json()
    except Exception:
        return web.Response(status=400, text="Bad Request: Invalid JSON")

    try:
        update = Update.de_json(data, app.bot)
        if update:
            await app.process_update(update)
    except Exception as e:
        logger.error(f"Error processing admin update: {e}", exc_info=True)

    return web.Response(text="OK")

async def health_check(request: web.Request) -> web.Response:
    return web.json_response({
        "status": "healthy",
        "system": "iSwitch Telegram Commerce",
        "channel": TELEGRAM_CHANNEL
    })

async def init_app():
    await db.init_db()
    await seed_initial_data()

    cust_app = create_customer_bot_app()
    admin_app = create_admin_bot_app()

    if cust_app and admin_app:
        notifier.register_bots(cust_app, admin_app)
        await cust_app.initialize()
        await admin_app.initialize()

        if WEBHOOK_URL:
            # Set webhook on Telegram
            await cust_app.bot.set_webhook(
                url=f"{WEBHOOK_URL}/webhook/customer",
                secret_token=WEBHOOK_SECRET,
                drop_pending_updates=True
            )
            await admin_app.bot.set_webhook(
                url=f"{WEBHOOK_URL}/webhook/admin",
                secret_token=WEBHOOK_SECRET,
                drop_pending_updates=True
            )
            logger.info("Webhooks registered successfully with Telegram servers.")

    server = web.Application()
    server["customer_app"] = cust_app
    server["admin_app"] = admin_app

    server.router.add_post("/webhook/customer", customer_webhook)
    server.router.add_post("/webhook/admin", admin_webhook)
    server.router.add_get("/health", health_check)

    return server

if __name__ == "__main__":
    server_app = web.run_app(init_app(), port=WEBHOOK_PORT)
