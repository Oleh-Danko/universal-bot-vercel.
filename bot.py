# bot.py
import os
import asyncio
import logging
from typing import List, Dict
from aiohttp import web

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

from live_parser import fetch_all_sources_grouped

# ---------- ЛОГИ ----------
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s:%(name)s:%(message)s"
)
log = logging.getLogger("news-bot")

# ---------- ENV ----------
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
WEBHOOK_BASE = os.environ.get("WEBHOOK_URL")  # напр. https://universal-bot-live.onrender.com

if not BOT_TOKEN or not WEBHOOK_BASE:
    raise RuntimeError("BOT_TOKEN і WEBHOOK_URL мають бути задані в Environment Variables.")

WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"{WEBHOOK_BASE}{WEBHOOK_PATH}"

# ---------- BOT/DP (aiogram 3) ----------
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

# ---------- ХЕНДЛЕРИ ----------
@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "👋 Привіт! Я збираю актуальні новини з перевірених джерел.\n"
        "Надішли /news щоб отримати свіжу стрічку прямо зараз."
    )

def _chunk_messages(lines: List[str], hard_limit: int = 3800) -> List[str]:
    """
    Розбиває великий список рядків на шматки до ~3800 символів,
    щоб не перевищити ліміт Telegram (4096).
    """
    chunks = []
    block = ""
    for line in lines:
        if len(block) + len(line) + 1 > hard_limit:
            if block:
                chunks.append(block.rstrip())
            block = line + "\n"
        else:
            block += line + "\n"
    if block.strip():
        chunks.append(block.rstrip())
    return chunks

@dp.message(Command("news"))
async def cmd_news(message: Message):
    # Попередження користувачу
    await message.answer("⏳ Збираю актуальні новини прямо зараз… (10 джерел)")

    try:
        grouped = await fetch_all_sources_grouped()
        # grouped: Dict[source_name, List[Dict{title, link, desc}]]

        if not any(grouped.values()):
            await message.answer("⚠️ Не вдалося отримати новини. Спробуй ще раз за хвилину.")
            return

        # Формуємо повідомлення з групуванням по джерелах
        all_lines: List[str] = ["📰 <b>Актуальні новини (живий парсинг)</b>"]
        total = 0

        order = [
            "BBC (Business)",
            "Reuters (Business)",
            "Reuters (Markets)",
            "Reuters (Technology)",
            "FT (Companies)",
            "FT (Markets)",
            "FT (Technology)",
            "FT (Opinion)",
            "Epravda (Finances)",
            "Epravda (Columns)",
        ]

        # додамо відсутні джерела в кінці (на випадок, якщо з'являться інші)
        for k in grouped.keys():
            if k not in order:
                order.append(k)

        for source in order:
            items = grouped.get(source, [])
            if not items:
                continue
            all_lines.append(f"\n<b>— {source}</b>")
            for it in items:
                title = it["title"].strip()
                link = it["link"].strip()
                desc = (it.get("desc") or "").strip()

                if desc:
                    all_lines.append(f"• <a href=\"{link}\">{title}</a>\n    — {desc}")
                else:
                    all_lines.append(f"• <a href=\"{link}\">{title}</a>")
                total += 1

        # Розсилка пачками
        for part in _chunk_messages(all_lines):
            await message.answer(part, disable_web_page_preview=False)

        await message.answer(f"✅ Надіслано: {total} новин із 10 джерел.")
    except Exception as e:
        logging.exception("news failed")
        await message.answer("⚠️ Не вдалося отримати новини. Спробуй ще раз за хвилину.")

# ---------- HEALTH ----------
async def handle_health(request):
    return web.Response(text="OK", status=200)

# ---------- START/STOP ----------
async def on_startup(app: web.Application):
    log.info(f"🌐 Starting bot, setting webhook to {WEBHOOK_URL}")
    await bot.set_webhook(WEBHOOK_URL)
    log.info("✅ Webhook set successfully")

async def on_shutdown(app: web.Application):
    log.info("🔻 Deleting webhook & closing session…")
    try:
        await bot.delete_webhook()
    except Exception:
        pass
    await bot.session.close()
    log.info("✅ Shutdown complete")

# ---------- AIOHTTP APP ----------
def main():
    app = web.Application()

    # Підключаємо aiogram до aiohttp
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)

    # healthcheck
    app.router.add_get("/", handle_health)
    app.router.add_get("/healthz", handle_health)

    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)

    # ГОЛОВНЕ: слухаємо порт з ENV (Render)
    port = int(os.environ.get("PORT", "10000"))
    log.info(f"🚀 Starting web server on 0.0.0.0:{port}")
    web.run_app(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    main()