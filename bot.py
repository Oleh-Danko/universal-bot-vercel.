import os
import logging
from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message
from bloomberg_parser import fetch_bloomberg

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("WebhookBot")

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://universal-bot-live.onrender.com")

if not BOT_TOKEN:
    raise RuntimeError("Environment variable BOT_TOKEN is required")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ✅ Health Check endpoint for Render
async def handle_health(request):
    return web.Response(text="OK")

# ✅ Start command
@dp.message(Command("start"))
async def start_cmd(message: Message):
    await message.answer(
        "👋 Привіт! Я бот, запущений на Render. Тепер я використовую стабільний Webhook!\n"
        "Надішліть /news, щоб перевірити парсинг."
    )

# ✅ News command
@dp.message(Command("news"))
async def news_cmd(message: Message):
    await message.answer("⏳ Отримую свіжі новини з Bloomberg...")
    try:
        news_list = await fetch_bloomberg(top_n=5)
        if not news_list:
            raise ValueError("Порожній список новин")

        text = "\n\n".join([f"📰 <b>{n['title']}</b>\n{n['link']}" for n in news_list])
        await message.answer(text, parse_mode="HTML")

    except Exception as e:
        logger.exception("Помилка в /news: %s", e)
        await message.answer(f"❌ Парсинг не вдався. Деталі помилки: {e}")

# ✅ Webhook handler
async def webhook_handler(request):
    update = await request.json()
    await dp.feed_webhook_update(bot, update)
    return web.Response()

# ✅ Launch web server (Render)
async def main():
    app = web.Application()
    app.router.add_get("/", handle_health)
    app.router.add_post(f"/webhook/{BOT_TOKEN}", webhook_handler)

    await bot.delete_webhook(drop_pending_updates=True)
    await bot.set_webhook(f"{WEBHOOK_URL}/webhook/{BOT_TOKEN}")
    logger.info("✅ Webhook successfully set.")

    web.run_app(app, host="0.0.0.0", port=int(os.getenv("PORT", 10000)))

if __name__ == "__main__":
    logger.info("🌐 Starting web server on 0.0.0.0:10000...")
    import asyncio
    asyncio.run(main())