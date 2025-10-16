import os
import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties # ✅ НОВИЙ ІМПОРТ: Для коректної ініціалізації
from aiohttp import web 
import requests 
from bs4 import BeautifulSoup 
# ---------------------------------------

# НОВИЙ ІМПОРТ: Підключаємо адаптивний парсер
from bloomberg_parser import fetch_bloomberg 

# --- Ініціалізація бота (ВИПРАВЛЕНО) ---
# 🔑 Тепер беремо змінну BOT_TOKEN
TOKEN = os.environ.get("BOT_TOKEN") 

if not TOKEN:
    # ❌ Жорстко зупиняємо, якщо токен не знайдено, з новою помилкою
    raise ValueError("❌ Environment variable BOT_TOKEN not found! Please set it on Render.")

# ✅ ВИПРАВЛЕНО: Використовуємо 'default=DefaultBotProperties()' замість 'parse_mode=...'
# Згідно з вимогами aiogram 3.7+
bot = Bot(
    token=TOKEN, 
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()
# ---------------------------------------


# --- Обробники команд ---

@dp.message(Command("start"))
async def start_command(message: types.Message):
    await message.answer(
        "👋 Привіт! Я бот, запущений на Render. Я не сплю, бо маю веб-сервер!\n"
        "Надішліть /news, щоб перевірити, чи працює основна логіка (з парсингом)."
    )

@dp.message(Command("news"))
async def news_command(message: types.Message):
    await message.answer("⏳ Отримую свіжі новини з Bloomberg...")
    try:
        # Припускаємо, що fetch_bloomberg повертає список заголовків, або порожній список/None
        titles = await fetch_bloomberg() 
        
        # Перевіряємо, чи повернулися новини
        if titles and isinstance(titles, list):
            formatted = "\n\n".join([f"🔹 {t}" for t in titles])
            await message.answer(f"📰 Топ новин Bloomberg:\n\n{formatted}")
        else:
            await message.answer("⚠️ Не вдалося отримати новини. Можливо, Bloomberg заблокував IP.")
            
    except Exception as e:
        # Це повідомлення для користувача. Деталі помилки підуть адміну
        await message.answer("❌ Парсинг не вдався. Адміністратора повідомлено про проблему.")
        # Тут має бути виклик функції send_admin_alert(f"Помилка в /news: {e}"), якщо вона є у коді

# --- Web Server для Render (щоб не засинав) ---

async def handle_ping(request):
    """Простий обробник для пінг-запитів Render"""
    return web.Response(text="✅ Bot is alive")

async def start_web_server():
    """Запускає веб-сервер на порту, який очікує Render (PORT)"""
    # Render передає порт через змінну оточення PORT
    port = int(os.environ.get("PORT", 8080)) 
    app = web.Application()
    app.router.add_get('/', handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    # Створюємо сайт
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"🌐 Keepalive running on port {port}")
    
    # Запобігаємо завершенню асинхронної функції
    while True:
        await asyncio.sleep(3600) # Чекаємо 1 годину

# --- Головна функція запуску ---

async def main():
    print("✅ Бот запущений і чекає повідомлень...")
    await asyncio.gather(
        dp.start_polling(bot),
        start_web_server() # Запуск фонового веб-сервера
    )

if __name__ == "__main__":
    # Запускаємо головну функцію
    asyncio.run(main())