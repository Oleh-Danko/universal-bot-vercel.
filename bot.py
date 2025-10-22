import os
import asyncio
import logging
from aiohttp import web

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

from news_parser import collect_all_news  # <-- наш живий парсер

# ====== ЛОГИ ======
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("news-bot")

# ====== ENV ======
BOT_TOKEN = os.environ.get("BOT_TOKEN")
WEBHOOK_BASE = os.environ.get("WEBHOOK_URL")  # напр. https://universal-bot-live.onrender.com
if not BOT_TOKEN or not WEBHOOK_BASE:
    raise RuntimeError("BOT_TOKEN і WEBHOOK_URL обов'язкові в Environment.")

WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"{WEBHOOK_BASE}{WEBHOOK_PATH}"

# ====== BOT/DP (aiogram 3.x) ======
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

# ====== HANDLERS ======
@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer("Привіт. Надішли /news — отримаєш свіжі новини з усіх джерел прямо зараз (без кешу).")

@dp.message(Command("news"))
async def cmd_news(message: Message):
    await message.answer("Збираю свіжі новини… Це може зайняти 5–15 сек (10 джерел).")

    try:
        news = await collect_all_news()  # живий парсинг тут
        if not news:
            await message.answer("Нічого не знайшов. Спробуй ще раз за хвилину.")
            return

        # відсортуємо (спочатку за джерелом, потім за назвою) — просто для стабільності виводу
        news.sort(key=lambda x: (x["source"], x["title"]))

        # чанкуємо під ліміт Телеграма
        CHUNK_LIMIT = 3900  # запас до 4096
        buf = ""
        current_source = None
        sent = 0

        async def flush():
            nonlocal buf, sent
            if buf.strip():
                await message.answer(buf, disable_web_page_preview=True)
                await asyncio.sleep(0.25)
                buf = ""

        for item in news:
            src = item["source"]
            if src != current_source:
                block_header = f"\n\n— <b>{src}</b> —\n"
            else:
                block_header = ""
            line = f"• <a href='{item['link']}'>{item['title']}</a>\n"
            to_add = block_header + line

            if len(buf) + len(to_add) > CHUNK_LIMIT:
                await flush()
            if src != current_source and len(block_header) > 0 and len(block_header) > CHUNK_LIMIT:
                # захист від абсурдних випадків
                pass
            buf += to_add
            current_source = src
            sent += 1

        await flush()
        await message.answer(f"Готово. Відправлено: {sent} новин.")

    except Exception as e:
        log.exception("Помилка в /news: %s", e)
        await message.answer(f"Сталася помилка під час парсингу: {e}")

# ====== HEALTH ======
async def handle_health(request):
    return web.Response(text="OK", status=200)

# ====== START/STOP ======
async def on_startup(app: web.Application):
    log.info(f"🌐 Starting bot, setting webhook to {WEBHOOK_URL}")
    await bot.set_webhook(WEBHOOK_URL)
    log.info("✅ Webhook set successfully")

async def on_shutdown(app: web.Application):
    log.info("Deleting webhook...")
    await bot.delete_webhook()
    await bot.session.close()
    log.info("✅ Shutdown complete")

# ====== MAIN ======
def main():
    app = web.Application()

    # реєстрація aiogram на aiohttp
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)

    # healthcheck для Render
    app.router.add_get("/", handle_health)
    app.router.add_get("/healthz", handle_health)

    port = int(os.environ.get("PORT", "10000"))
    log.info(f"🚀 Starting web server on 0.0.0.0:{port}")
    web.run_app(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    main()