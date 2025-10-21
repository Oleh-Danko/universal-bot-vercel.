import os
import asyncio
import logging
from aiohttp import web

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

# ====== ЛОГИ ======
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("news-bot")

# ====== ENV ======
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
WEBHOOK_BASE = os.environ.get("WEBHOOK_URL")  # наприклад https://universal-bot-live.onrender.com

if not BOT_TOKEN or not WEBHOOK_BASE:
    raise RuntimeError("BOT_TOKEN і WEBHOOK_URL обов'язкові в Environment.")

WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"{WEBHOOK_BASE}{WEBHOOK_PATH}"

# ====== BOT/DP (aiogram 3.x) ======
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

# ====== ХЕНДЛЕРИ ======
@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer("👋 Привіт! Надішли /news щоб отримати новини.")

@dp.message(Command("news"))
async def cmd_news(message: Message):
    # ТУТ ПРИКЛАД – віддай 3 рядки, щоб перевірити, що все працює. Потім підключимо кеш.
    text = (
        "📰 <b>Новини зараз недоступні з кешу</b>\n"
        "✅ Але вебхук і порт працюють.\n"
        "➡️ Далі підключимо кеш/парсер."
    )
    await message.answer(text, disable_web_page_preview=True)

# ====== HEALTHZ ======
async def handle_health(request):
    return web.Response(text="OK", status=200)

# ====== START/STOP HOOKS ======
async def on_startup(app: web.Application):
    log.info(f"Setting webhook to {WEBHOOK_URL}")
    await bot.set_webhook(WEBHOOK_URL)
    log.info("Webhook set ✅")

async def on_shutdown(app: web.Application):
    log.info("Deleting webhook...")
    await bot.delete_webhook()
    await bot.session.close()
    log.info("Shutdown complete ✅")

# ====== MAIN (AIOHTTP APP) ======
def main():
    app = web.Application()

    # реєструємо хендлери aiogram на aiohttp
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)

    # healthcheck для Render
    app.router.add_get("/", handle_health)        # GET /
    app.router.add_get("/healthz", handle_health) # GET /healthz

    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)

    # ГОЛОВНЕ: слухаємо саме порт з ENV
    port = int(os.environ.get("PORT", "10000"))
    log.info(f"🌐 Starting web server on 0.0.0.0:{port} ...")
    web.run_app(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    main()