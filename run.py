import sys
import asyncio
import logging
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from config import CUSTOMER_BOT_TOKEN, ADMIN_BOT_TOKEN, ADMIN_USER_IDS, TELEGRAM_CHANNEL
from database.db import db
from database.crud import seed_initial_data
from services.notifier import notifier
from customer_bot.bot import create_customer_bot_app
from admin_bot.bot import create_admin_bot_app

# Setup rich logging
logging.basicConfig(
    format="%(asctime)s - [%(name)s] - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("iswitch.main")

async def run_bots():
    logger.info("==================================================")
    logger.info("   Starting iSwitch Production Telegram Commerce   ")
    logger.info("==================================================")
    logger.info(f"Source Channel: {TELEGRAM_CHANNEL}")
    logger.info(f"Authorized Admin Telegram IDs: {ADMIN_USER_IDS}")

    # 1. Initialize Database Schema & Initial Data
    logger.info("Initializing database and seeding default data...")
    await db.init_db()
    await seed_initial_data()
    logger.info("Database initialized successfully.")

    # 2. Check Bot Tokens
    if not CUSTOMER_BOT_TOKEN or not ADMIN_BOT_TOKEN:
        logger.warning("\n" + "=" * 60)
        logger.warning("  WARNING: TELEGRAM BOT TOKENS NOT CONFIGURED")
        logger.warning("=" * 60)
        logger.warning("To launch the live bots:")
        logger.warning("1. Create your two bots via @BotFather on Telegram:")
        logger.warning("   - Customer Bot (for shoppers)")
        logger.warning("   - Admin Bot (for administrators)")
        logger.warning("2. Put the tokens in your .env file:")
        logger.warning("   CUSTOMER_BOT_TOKEN=123456:ABC-DEF...")
        logger.warning("   ADMIN_BOT_TOKEN=654321:XYZ-UVW...")
        logger.warning("=" * 60 + "\n")
        logger.info("System is ready and operational once tokens are set.")
        return

    # 3. Create bot applications
    logger.info("Initializing Customer Bot and Admin Bot...")
    cust_app = create_customer_bot_app()
    admin_app = create_admin_bot_app()

    # 4. Register apps with cross-bot notifier
    notifier.register_bots(cust_app, admin_app)

    # 5. Optional Healthcheck Web Server for Render / Cloud Platforms
    port_env = os.getenv("PORT")
    health_runner = None
    if port_env and port_env.isdigit():
        try:
            from aiohttp import web

            async def handle_health(request):
                return web.Response(
                    text="iSwitch Telegram Commerce Bot is Healthy & Online!\nStatus: 200 OK",
                    content_type="text/plain",
                    status=200
                )

            web_app = web.Application()
            web_app.router.add_get("/", handle_health)
            web_app.router.add_get("/health", handle_health)
            web_app.router.add_get("/healthz", handle_health)
            health_runner = web.AppRunner(web_app)
            await health_runner.setup()
            site = web.TCPSite(health_runner, "0.0.0.0", int(port_env))
            await site.start()
            logger.info(f"Healthcheck HTTP server running on 0.0.0.0:{port_env} (Render Web Service Ready)")
        except Exception as srv_err:
            logger.warning(f"Could not start healthcheck HTTP server on port {port_env}: {srv_err}")

    logger.info("Starting bots with concurrent long-polling...")

    # Run both apps concurrently
    await cust_app.initialize()
    await admin_app.initialize()

    await cust_app.start()
    await admin_app.start()

    await cust_app.updater.start_polling(drop_pending_updates=True)
    await admin_app.updater.start_polling(drop_pending_updates=True)

    logger.info("Both Customer Bot and Admin Bot are ONLINE and listening for updates!")

    # Keep running until cancelled
    stop_event = asyncio.Event()
    try:
        await stop_event.wait()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Shutdown requested...")
    finally:
        logger.info("Stopping bots gracefully...")
        if health_runner:
            try:
                await health_runner.cleanup()
            except Exception:
                pass
        await cust_app.updater.stop()
        await admin_app.updater.stop()
        await cust_app.stop()
        await admin_app.stop()
        await cust_app.shutdown()
        await admin_app.shutdown()
        logger.info("Shutdown complete.")

if __name__ == "__main__":
    try:
        asyncio.run(run_bots())
    except KeyboardInterrupt:
        print("\nExiting iSwitch Commerce System.")
