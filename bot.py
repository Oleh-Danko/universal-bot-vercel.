# bot.py
import os
import logging
from aiohttp import web
import asyncio

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

from live_parser import fetch_live_grouped, format_grouped_to_chunks

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
    await message.answer("👋 Привіт! Надішли /news щоб отримати новини з 10 джерел у реальному часі.")

@dp.message(Command("news"))
async def cmd_news(message: Message):
    await message.answer("⏳ Збираю актуальні новини прямо зараз… (10 джерел)")
    try:
        grouped = await fetch_live_grouped()
        chunks = format_grouped_to_chunks(grouped, max_chunk_len=3500)
        # надсилаємо частинами
        for i, text in enumerate(chunks, start=1):
            await message.answer(text, disable_web_page_preview=False)
    except Exception as e:
        log.warning(f"/news failed: {e}")
        await message.answer("⚠️ Не вдалося отримати новини. Спробуй ще раз за хвилину.")

# ====== HEALTHZ ======
async def handle_health(request):
    return web.Response(text="OK", status=200)

# ====== START/STOP HOOKS ======
async def on_startup(app: web.Application):
    log.info(f"🌐 Starting bot, setting webhook to {WEBHOOK_URL}")
    await bot.set_webhook(WEBHOOK_URL)
    log.info("✅ Webhook set successfully")

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

    # слухаємо PORT від Render
    port = int(os.environ.get("PORT", "10000"))
    log.info(f"🚀 Starting web server on 0.0.0.0:{port}")
    web.run_app(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    main()