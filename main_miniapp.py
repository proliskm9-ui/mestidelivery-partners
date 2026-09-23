import asyncio
import logging
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from config import BOT_TOKEN, HTTP_HOST, HTTP_PORT
from database import init_db
from handlers import start_router, admin_router
from http_server import make_http_app
from referral import process_delivered_orders

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


async def referral_order_watcher(bot: Bot):
    log.info("Starting referral_order_watcher background task...")
    while True:
        try:
            await asyncio.sleep(10)
            await process_delivered_orders(bot)
        except asyncio.CancelledError:
            log.info("referral_order_watcher cancelled")
            break
        except Exception as e:
            log.exception("Error in referral_order_watcher loop: %s", e)


async def main():
    await init_db()

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    dp.include_router(start_router)
    dp.include_router(admin_router)

    http_app = make_http_app(bot)
    runner = web.AppRunner(http_app)
    await runner.setup()
    site = web.TCPSite(runner, HTTP_HOST, HTTP_PORT)
    await site.start()
    log.info('Customer bot HTTP server listening on %s:%s', HTTP_HOST, HTTP_PORT)

    watcher_task = asyncio.create_task(referral_order_watcher(bot))

    await bot.delete_webhook(drop_pending_updates=True)
    try:
        await dp.start_polling(bot)
    finally:
        watcher_task.cancel()
        await runner.cleanup()


if __name__ == '__main__':
    asyncio.run(main())
