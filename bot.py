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
BOT_TOKEN = "8392167879:AAG9GgPCXrajvdZca5vJcYopk3HO5w2hBhE"
ADMIN_ID = 6680030792
WEBHOOK_BASE = "https://universal-bot-live.onrender.com"

WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"{WEBHOOK_BASE}{WEBHOOK_PATH}"

# ====== BOT ======
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

# ====== ХЕНДЛЕРИ ======
@dp.message(Command("start"))
async def start_cmd(message: Message):
    await message.answer("👋 Привіт! Надішли /news щоб отримати новини.")

@dp.message(Command("news"))
async def news_cmd(message: Message):
    text = (
        "📰 <b>Новини зараз недоступні з кешу</b>\n"
        "✅ Але вебхук і порт працюють.\n"
        "➡️ Далі підключимо кеш/парсер."
    )
    await message.answer(text, disable_web_page_preview=True)

# ====== HEALTH CHECK ======
async def handle_health(request):
    return web.Response(text="OK", status=200)

# ====== STARTUP / SHUTDOWN ======
async def on_startup(app: web.Application):
    log.info(f"🌐 Starting bot, setting webhook to {WEBHOOK_URL}")
    await bot.set_webhook(WEBHOOK_URL)
    log.info("✅ Webhook set successfully")

async def on_shutdown(app: web.Application):
    log.info("💤 Shutting down bot and deleting webhook...")
    await bot.delete_webhook()
    await bot.session.close()
    log.info("✅ Bot stopped")

# ====== MAIN ======
def main():
    app = web.Application()

    # підключаємо aiogram до aiohttp
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)

    # health endpoints для Render
    app.router.add_get("/", handle_health)
    app.router.add_get("/healthz", handle_health)

    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)

    # обов’язково слухаємо порт з Render
    port = int(os.environ.get("PORT", "10000"))
    log.info(f"🚀 Starting web server on 0.0.0.0:{port}")
    web.run_app(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    main()