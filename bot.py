import os
import asyncio
import logging
from datetime import datetime
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from cache_manager import CacheManager, run_cache_update
from rss_parser import fetch_rss_news

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("WebhookBot")

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_BASE = os.getenv("WEBHOOK_URL")
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"{WEBHOOK_BASE}{WEBHOOK_PATH}"

bot = Bot(token=BOT_TOKEN, parse_mode="HTML")
dp = Dispatcher()
cache_manager = CacheManager()

RSS_SOURCES = [
    "https://epravda.com.ua/finances",
    "https://epravda.com.ua/columns",
    "https://www.reuters.com/business",
    "https://www.reuters.com/markets",
    "https://www.reuters.com/technology",
    "https://www.ft.com/companies",
    "https://www.ft.com/technology",
    "https://www.ft.com/markets",
    "https://www.ft.com/opinion",
    "https://www.bbc.com/business",
]

async def run_parser_background():
    logger.info("Updating news cache...")
    await run_cache_update()
    while True:
        await asyncio.sleep(3600)
        try:
            logger.info("Updating news cache...")
            await run_cache_update()
        except Exception as e:
            logger.error(f"Error during update: {e}")

@dp.message(Command("start"))
async def start_cmd(message: Message):
    await message.answer(
        "👋 Привіт! Надішліть /news, щоб отримати останні новини."
    )

@dp.message(Command("news"))
async def news_cmd(message: Message):
    await message.answer("✅ Завантажую кеш новин...")
    cache_data = cache_manager.load_cache()
    articles = cache_data.get('articles', [])
    timestamp = cache_data.get('timestamp', 'Невідомо')
    if isinstance(timestamp, str):
        timestamp = timestamp[:16].replace('T', ' ')
    if not articles:
        await message.answer("❌ Кеш порожній. Спробуйте пізніше.")
        return

    formatted_chunk = ""
    TELEGRAM_CHUNK_LIMIT = 4000
    current_source_title = None

    await message.answer(f"📰 Останні новини (оновлено: {timestamp})")

    for article in articles:
        source_header = ""
        if article['source'] != current_source_title:
            source_header = f"\n-- {article['source']} --\n"
            current_source_title = article['source']

        link_text = article['link']
        if 'bbc.co.uk' in link_text:
            link_text = link_text.split('?at_medium')[0]

        article_text = f"📰 <b>{article['title']}</b>\n<a href='{link_text}'>Читати повністю</a>\n"

        if len(formatted_chunk) + len(source_header) + len(article_text) > TELEGRAM_CHUNK_LIMIT:
            if formatted_chunk.strip():
                await message.answer(formatted_chunk, parse_mode="HTML", disable_web_page_preview=True)
                await asyncio.sleep(0.3)
            formatted_chunk = source_header + article_text
        else:
            formatted_chunk += source_header + article_text

    if formatted_chunk.strip():
        await message.answer(formatted_chunk, parse_mode="HTML", disable_web_page_preview=True)
    await message.answer(f"✅ Успішно надіслано {len(articles)} новин.")

async def on_startup(app):
    await bot.set_webhook(WEBHOOK_URL)
    asyncio.create_task(run_parser_background())

async def on_shutdown(app):
    await bot.delete_webhook()
    await bot.session.close()

async def handle_health(request):
    return web.Response(text="✅ OK", status=200)

def main():
    app = web.Application()
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)
    app.router.add_get("/", handle_health)
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    port = int(os.getenv("PORT", 10000))
    web.run_app(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    main()