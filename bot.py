import os
import asyncio
import logging
from aiohttp import web

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

from live_parser import fetch_epravda_finances  # <-- тільки epravda

# ====== ЛОГИ ======
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("news-bot")

# ====== ENV ======
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
WEBHOOK_BASE = os.environ.get("WEBHOOK_URL")  # типу: https://universal-bot-live.onrender.com

if not BOT_TOKEN or not WEBHOOK_BASE:
    raise RuntimeError("BOT_TOKEN і WEBHOOK_URL обов'язкові в Environment.")

WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"{WEBHOOK_BASE}{WEBHOOK_PATH}"

# ====== BOT/DP ======
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

# ====== ХЕНДЛЕРИ ======
@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer("👋 Привіт! Надішли /news — отримаєш актуальні новини з Економічної Правди (розділ «Фінанси»).")

@dp.message(Command("news"))
async def cmd_news(message: Message):
    await message.answer("⏳ Збираю новини з Epravda /finances …")

    try:
        items = await fetch_epravda_finances()  # тільки epravda /finances
        if not items:
            await message.answer("⚠️ Не знайшов новин на epravda /finances. Спробуй ще раз за хвилину.")
            return

        # Групуємо одним блоком "Epravda (Finances)"
        lines = []
        for it in items:
            title = it.get("title", "").strip()
            link = it.get("link", "").strip()
            desc = it.get("desc", "").strip()
            if desc:
                lines.append(f"• <a href=\"{link}\">{title}</a> — {desc}")
            else:
                lines.append(f"• <a href=\"{link}\">{title}</a>")

        # Розбиваємо на кілька повідомлень, щоб не впертися в ліміт 4096 символів
        header = "<b>Epravda (Finances)</b>\n"
        chunk = header
        for line in lines:
            if len(chunk) + len(line) + 1 > 3900:
                await message.answer(chunk, disable_web_page_preview=True)
                chunk = header
            chunk += line + "\n"
        if chunk.strip():
            await message.answer(chunk, disable_web_page_preview=True)

    except Exception as e:
        log.exception("news handler error")
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
    log.info("🔻 Deleting webhook & closing session…")
    await bot.delete_webhook()
    await bot.session.close()
    log.info("✅ Shutdown complete")

# ====== MAIN (AIOHTTP APP) ======
def main():
    app = web.Application()

    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)

    app.router.add_get("/", handle_health)
    app.router.add_get("/healthz", handle_health)

    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)

    port = int(os.environ.get("PORT", "10000"))
    log.info(f"🚀 Starting web server on 0.0.0.0:{port}")
    web.run_app(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    main()