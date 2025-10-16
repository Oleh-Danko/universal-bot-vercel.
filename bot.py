import os
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiohttp import web 
import logging

# Підключаємо адаптивний парсер
from bloomberg_parser import fetch_bloomberg 

# Налаштування логування
logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger("WebhookBot")

# --- Конфігурація ---
TOKEN = os.environ.get("BOT_TOKEN") 
if not TOKEN:
    raise ValueError("❌ Environment variable BOT_TOKEN not found! Please set it on Render.")

# URL вашого сервісу на Render (КРИТИЧНО ВАЖЛИВО!)
# !!! ПЕРЕВІРТЕ ЦЕЙ URL: https://universal-bot-live.onrender.com !!!
WEBHOOK_HOST = 'https://universal-bot-live.onrender.com'
WEBHOOK_PATH = f'/webhook/{TOKEN}'
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"

# Ініціалізація
bot = Bot(
    token=TOKEN, 
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

# --- Обробники команд ---

@dp.message(Command("start"))
async def start_command(message: types.Message):
    await message.answer(
        "👋 Привіт! Я бот, запущений на Render. Тепер я використовую стабільний Webhook!\n"
        "Надішліть /news, щоб перевірити парсинг."
    )

@dp.message(Command("news"))
async def news_command(message: types.Message):
    await message.answer("⏳ Отримую свіжі новини з Bloomberg...")
    try:
        # fetch_bloomberg тепер повертає список dict: [{"title": "...", "url": "..."}]
        headlines = await fetch_bloomberg(top_n=10) 
        
        if headlines:
            formatted = "\n\n".join([f"🔹 <a href='{h['url']}'>{h['title']}</a>" for h in headlines if h.get('url')])
            # Якщо заголовки є, але немає URL (що малоймовірно з новим парсером)
            if not formatted:
                formatted = "\n\n".join([f"🔹 {h['title']}" for h in headlines])
            
            await message.answer(f"📰 Топ новин Bloomberg:\n\n{formatted}", disable_web_page_preview=True)
        else:
            await message.answer("⚠️ Не вдалося отримати новини. Можливо, сайт заблокував запит або сталася помилка.")
            
    except Exception as e:
        LOG.error(f"Помилка в /news: {e}")
        # Тут можна було б надіслати помилку адміну, але поки виводимо користувачу
        await message.answer(f"❌ Парсинг не вдався. Деталі помилки: {e}")

# --- Webhook Handler та Запуск Сервера ---

async def telegram_webhook_handler(request: web.Request):
    """Обробник, який приймає POST-запити від Telegram."""
    try:
        # 1. Отримуємо оновлення у форматі JSON
        data = await request.json()
        # 2. Перетворюємо JSON на об'єкт Update
        update = types.Update(**data)
        # 3. Передаємо оновлення в диспетчер aiogram для обробки
        await dp.feed_update(bot, update)
    except Exception as e:
        LOG.error(f"Error handling webhook: {e}")
    
    # Telegram очікує 200 OK
    return web.Response()

async def on_startup(app: web.Application):
    """Дія при запуску: встановлюємо Webhook у Telegram."""
    LOG.info(f"Setting webhook to {WEBHOOK_URL}")
    await bot.set_webhook(WEBHOOK_URL)
    LOG.info("✅ Webhook successfully set.")

async def on_shutdown(app: web.Application):
    """Дія при зупинці: видаляємо Webhook."""
    LOG.info("Deleting webhook...")
    await bot.delete_webhook()
    LOG.info("✅ Webhook successfully deleted.")


def main():
    """Основна функція запуску Webhook сервера."""
    
    # 1. Створюємо додаток aiohttp
    app = web.Application()
    
    # 2. Додаємо POST-обробник для шляху /webhook/{TOKEN}
    app.router.add_post(WEBHOOK_PATH, telegram_webhook_handler)
    
    # 3. Реєструємо функції запуску/зупинки
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    
    # 4. Визначаємо порт (обов'язково беремо PORT зі змінних середовища Render)
    port = int(os.environ.get("PORT", 8080))
    
    LOG.info(f"🌐 Starting web server on 0.0.0.0:{port}...")
    
    # 5. Запускаємо aiohttp веб-сервер
    web.run_app(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    main()