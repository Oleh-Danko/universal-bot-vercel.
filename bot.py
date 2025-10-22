import os
import asyncio
import logging
from aiohttp import web

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

from live_parser import fetch_all_sources, chunk_messages

# ====== ЛОГИ (видно у Render → Logs) ======
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s: %(message)s")
log = logging.getLogger("news-bot")

# ====== ENV ======
BOT_TOKEN = os.environ.get("BOT_TOKEN")  # 8392167879:AAG9GgPCXrajvdZca5vJcYopk3HO5w2hBhE
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))  # 6680030792
WEBHOOK_BASE = os.environ.get("WEBHOOK_URL")    # https://universal-bot-live.onrender.com

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
    await message.answer("👋 Привіт! Надішли /news щоб ЗАРАЗ зібрати свіжі новини з 10 джерел.")

@dp.message(Command("news"))
async def cmd_news(message: Message):
    await message.answer("⏳ Збираю актуальні новини прямо зараз… (10 джерел)")
    try:
        articles = await fetch_all_sources()
        if not articles:
            await message.answer("❌ Нічого не знайшов. Спробуй ще раз трохи пізніше.")
            return

        # формуємо повідомлення й ріжемо по 4000 символів
        lines = [f"• <a href='{a['link']}'>{a['title']}</a> <i>({a['source']})</i>" for a in articles]
        text = "📰 <b>Актуальні новини (живий парсинг)</b>\n\n" + "\n".join(lines)

        for chunk in chunk_messages(text, limit=4000):
            await message.answer(chunk, disable_web_page_preview=True)
            await asyncio.sleep(0.2)
        await message.answer(f"✅ Надіслано: {len(articles)} новин з 10 джерел.")
    except Exception as e:
        log.exception("Помилка в /news: %s", e)
        await message.answer("💥 Сталася помилка під час парсингу. Спробуй ще раз.")

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
    log.info("✅ Shutdown complete")

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

    # СЛУХАЄМО САМЕ ЦЕЙ ПОРТ!
    port = int(os.environ.get("PORT", "10000"))
    log.info(f"🚀 Starting web server on 0.0.0.0:{port}")
    web.run_app(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    main()