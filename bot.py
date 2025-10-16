import os
import logging
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

from bloomberg_parser import fetch_bloomberg

# === CONFIG & INIT ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("WebhookBot")

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("Environment variable BOT_TOKEN is required")

# Використовуємо WEBHOOK_URL зі змінних оточення (Render)
WEBHOOK_BASE = os.getenv("WEBHOOK_URL", "https://universal-bot-live.onrender.com")

WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"{WEBHOOK_BASE}{WEBHOOK_PATH}"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# === HANDLERS ===
@dp.message(Command("start"))
async def start_cmd(message: Message):
    await message.answer(
        "👋 Привіт! Я бот, запущений на Render. Надішліть /news, щоб перевірити парсинг."
    )

@dp.message(Command("news"))
async def news_cmd(message: Message):
    await message.answer("⏳ Отримую свіжі новини з Bloomberg...")
    try:
        news_list = await fetch_bloomberg(top_n=5)
        if not news_list:
            raise ValueError("Порожній список новин")

        formatted_news = []
        for n in news_list:
            formatted_news.append(f"📰 <b>{n['title']}</b>\n<a href='{n['link']}'>Читати на Bloomberg</a>")

        text = "\n\n".join(formatted_news)
        await message.answer(text, parse_mode="HTML", disable_web_page_preview=True)

    except Exception as e:
        logger.exception("Помилка в /news: %s", e)
        await message.answer(f"❌ Парсинг не вдався. Деталі помилки: {e}")


# === STARTUP / SHUTDOWN (Async Operations) ===
async def on_startup(app):
    # Встановлюємо webhook
    logger.info(f"Setting webhook to {WEBHOOK_URL}")
    await bot.set_webhook(WEBHOOK_URL)
    logger.info("✅ Webhook successfully set.")

async def on_shutdown(app):
    # Видаляємо webhook перед зупинкою
    logger.info("Deleting webhook...")
    await bot.delete_webhook()
    await bot.session.close()
    logger.info("✅ Shutdown complete.")

# === HEALTH CHECK ===
async def handle_health(request):
    return web.Response(text="✅ OK", status=200)

# === MAIN (Synchronous Server Run) ===
def main():
    app = web.Application()

    # Реєстрація хендлерів Webhook та Диспетчера
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)

    # Health Check Endpoint
    app.router.add_get("/", handle_health)

    # Реєстрація функцій on_startup та on_shutdown
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)

    logger.info("🌐 Starting web server on 0.0.0.0:10000 ...")
    # web.run_app() сам запускає цикл подій, тут немає asyncio.run()
    web.run_app(app, host="0.0.0.0", port=int(os.getenv("PORT", 10000)))

if __name__ == "__main__":
    main()