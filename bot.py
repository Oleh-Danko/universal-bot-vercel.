# bot.py
import os
import logging
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

from bloomberg_parser import fetch_bloomberg  # our parser (expects top_n param)

logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger("WebhookBot")

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("Environment variable BOT_TOKEN is required")

# WEBHOOK_URL should be base URL (e.g. https://universal-bot-live.onrender.com)
WEBHOOK_BASE = os.getenv("WEBHOOK_URL")
if not WEBHOOK_BASE:
    raise RuntimeError("Environment variable WEBHOOK_URL is required (base URL)")

WEBHOOK_BASE = WEBHOOK_BASE.rstrip("/")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ---------- Handlers ----------
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("👋 Привіт! Я бот, запущений на Render через Webhook. Надішліть /news")

@dp.message(Command("news"))
async def cmd_news(message: types.Message):
    await message.answer("⏳ Отримую свіжі новини з Bloomberg...")
    try:
        headlines = await fetch_bloomberg(top_n=10)
        if not headlines:
            await message.answer("❌ Парсинг не вдався. Можливо, сайт заблокував запит або сталася помилка.")
            return
        formatted = "\n\n".join([f"🔹 {t}" for t in headlines])
        await message.answer(f"📰 Топ новин Bloomberg:\n\n{formatted}")
    except Exception as e:
        LOG.exception("Помилка в /news")
        await message.answer(f"❌ Помилка при парсингу: {e}")

# ---------- Webhook & Health ----------
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"{WEBHOOK_BASE}{WEBHOOK_PATH}"

async def on_startup(app: web.Application):
    # встановлюємо webhook
    await bot.set_webhook(WEBHOOK_URL)
    LOG.info("Setting webhook to %s", WEBHOOK_URL)

async def on_shutdown(app: web.Application):
    try:
        await bot.delete_webhook()
        LOG.info("Webhook deleted")
    except Exception:
        LOG.exception("Error deleting webhook")

async def health(request):
    return web.Response(text="OK", status=200)

# Create app
app = web.Application()
# health endpoints for Render
app.router.add_get("/", health)
app.router.add_get("/health", health)

# register webhook handler at path
SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)
setup_application(app, dp, bot=bot)

app.on_startup.append(on_startup)
app.on_shutdown.append(on_shutdown)

if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    LOG.info("🌐 Starting web server on 0.0.0.0:%d", port)
    web.run_app(app, host="0.0.0.0", port=port)