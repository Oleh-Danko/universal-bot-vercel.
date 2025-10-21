import os
import asyncio
import logging
from aiohttp import web

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

from cache_manager import CacheManager, run_cache_update

# ====== ЛОГИ ======
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("news-bot")

# ====== ENV ======
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
WEBHOOK_BASE = os.environ.get("WEBHOOK_URL", "").strip()  # наприклад https://universal-bot-live.onrender.com
if not BOT_TOKEN or not WEBHOOK_BASE:
    raise RuntimeError("BOT_TOKEN і WEBHOOK_URL обов'язкові в Environment.")

WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"{WEBHOOK_BASE}{WEBHOOK_PATH}"

# ====== BOT/DP (aiogram 3.x) ======
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

cache = CacheManager()

# ====== УТІЛІТА: відправити довгий текст частинами ======
TELEGRAM_CHUNK_LIMIT = 4000

async def send_long_message(chat_id: int, text: str):
    if len(text) <= TELEGRAM_CHUNK_LIMIT:
        await bot.send_message(chat_id, text, disable_web_page_preview=True)
        return
    start = 0
    end = TELEGRAM_CHUNK_LIMIT
    while start < len(text):
        await bot.send_message(chat_id, text[start:end], disable_web_page_preview=True)
        await asyncio.sleep(0.2)
        start = end
        end = min(end + TELEGRAM_CHUNK_LIMIT, len(text))

# ====== ХЕНДЛЕРИ ======
@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer("👋 Привіт! Надішли /news щоб отримати останні новини з BBC, Reuters, FT та ЕП.")

@dp.message(Command("news"))
async def cmd_news(message: Message):
    data = cache.load_cache()
    items = data.get("articles", [])
    ts = data.get("timestamp", "невідомо")

    if not items:
        await message.answer(
            "📰 <b>Кеш новин порожній</b>\n"
            "⏳ Я вже оновлюю новини у фоні. Спробуй ще раз за хвилину.",
            disable_web_page_preview=True
        )
        return

    # групуємо за source і віддаємо все, що є
    items.sort(key=lambda x: (x.get("source",""), x.get("title","")))
    header = f"📰 <b>Оновлено:</b> {ts}\n<b>Усього:</b> {len(items)} статей\n\n"
    await message.answer(header, disable_web_page_preview=True)

    current_source = None
    block = ""
    for it in items:
        src = it.get("source", "Unknown")
        title = it.get("title", "").strip()
        link  = it.get("link", "").strip()

        # якщо змінюється джерело — відправляємо накопичене
        if src != current_source:
            if block.strip():
                await send_long_message(message.chat.id, block)
                block = ""
            block += f"\n— <b>{src}</b> —\n"
            current_source = src

        # рядок статті
        if title and link:
            line = f"• <a href='{link}'>{title}</a>\n"
            # якщо наступне додавання перевищить ліміт — шлемо блок і відкриваємо новий
            if len(block) + len(line) > TELEGRAM_CHUNK_LIMIT:
                await send_long_message(message.chat.id, block)
                block = f"\n— <b>{src}</b> —\n" + line
            else:
                block += line

    if block.strip():
        await send_long_message(message.chat.id, block)

    await message.answer("✅ Готово. Якщо треба — пиши /news ще раз.")

# ====== HEALTHZ ======
async def handle_health(request):
    return web.Response(text="OK", status=200)

# ====== ФОНОВА ЗАДАЧА ОНОВЛЕННЯ КЕШУ ======
async def background_cache_loop():
    # перше оновлення відразу
    try:
        await run_cache_update()
        log.info("Initial cache update done.")
    except Exception as e:
        log.exception("Initial cache update failed: %s", e)

    # далі щогодини
    while True:
        await asyncio.sleep(3600)
        try:
            await run_cache_update()
            log.info("Scheduled cache update done.")
        except Exception as e:
            log.exception("Scheduled cache update failed: %s", e)

# ====== START/STOP HOOKS ======
async def on_startup(app: web.Application):
    log.info(f"Setting webhook to {WEBHOOK_URL}")
    await bot.set_webhook(WEBHOOK_URL)
    log.info("Webhook set ✅")
    # запускаємо фонове оновлення кешу
    asyncio.create_task(background_cache_loop())

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

    # слухаємо порт від Render
    port = int(os.environ.get("PORT", "10000"))
    log.info(f"🌐 Starting web server on 0.0.0.0:{port} ...")
    web.run_app(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    main()