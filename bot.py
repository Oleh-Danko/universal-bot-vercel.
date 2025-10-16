import logging
import os
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from bloomberg_parser import fetch_bloomberg

API_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # https://universal-bot-live.onrender.com/webhook

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# === Команди ===
@dp.message(commands=['start'])
async def start_cmd(message: types.Message):
    await message.answer("👋 Бот активний і працює через Webhook!")

@dp.message(commands=['news'])
async def get_news(message: types.Message):
    try:
        headlines = await fetch_bloomberg()
        if not headlines:
            await message.answer("⚠️ Не вдалося отримати новини. Можливо, сайт заблокував запит або сталася помилка.")
            return
        formatted = "\n".join([f"• {t}" for t in headlines[:10]])
        await message.answer(f"📰 Останні новини Bloomberg:\n\n{formatted}")
    except Exception as e:
        logging.exception("Помилка під час виконання /news")
        await message.answer(f"❌ Помилка: {e}")

# === Створення aiohttp застосунку ===
async def on_startup(app):
    await bot.set_webhook(WEBHOOK_URL)
    logging.info(f"Webhook встановлено: {WEBHOOK_URL}")

async def on_shutdown(app):
    await bot.delete_webhook()
    logging.info("Webhook видалено")

app = web.Application()

# ✅ HEALTHCHECK endpoint (для Render)
async def healthcheck(request):
    return web.Response(text="OK", status=200)

app.router.add_get("/", healthcheck)
app.router.add_get("/health", healthcheck)

# === Webhook handler ===
SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path="/webhook")
setup_application(app, dp, bot=bot)

app.on_startup.append(on_startup)
app.on_shutdown.append(on_shutdown)

if __name__ == "__main__":
    web.run_app(app, host="0.0.0.0", port=int(os.getenv("PORT", 10000)))