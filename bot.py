import os
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiohttp import web 
# --- ДОДАНІ БІБЛІОТЕКИ ДЛЯ ПАРСИНГУ ---
import requests
from bs4 import BeautifulSoup
# ---------------------------------------

# 🔑 Токен береться зі змінних оточення Render (це безпечно)
TOKEN = os.environ.get("TOKEN") 

if not TOKEN:
    print("Помилка: Не знайдено змінну оточення TOKEN. Перевірте Render settings.")
    exit(1)

# Режим розбору Markdown для форматування
bot = Bot(token=TOKEN)
dp = Dispatcher()

# --- Обробники команд ---

@dp.message(Command("start"))
async def start_command(message: types.Message):
    await message.answer(
        "👋 Привіт! Я бот, запущений на Render. Я не сплю, бо маю веб-сервер!\n"
        "Надішліть /news, щоб перевірити, чи працює основна логіка (з парсингом)."
    )

@dp.message(Command("news"))
async def news_command(message: types.Message):
    # --- НОВА ЛОГІКА ПАРСИНГУ ---
    try:
        # Використовуємо розділ Markets з Bloomberg
        url = "https://www.bloomberg.com/markets" # [cite: 2025-10-14]
        
        # Використовуємо requests, щоб отримати HTML сторінки
        response = requests.get(url)
        response.raise_for_status() # Перевірка, чи не було помилок HTTP
        
        # Розбір HTML за допомогою BeautifulSoup
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Спрощений пошук заголовка (потрібен актуальний клас)
        # На Bloomberg заголовок часто має клас 'headline' або просто знаходиться в h1/h2
        headline_element = soup.find(['h1', 'h2'], class_='headline') or soup.find('h1')
        
        if headline_element:
            text = f"📰 Остання новина з Bloomberg (Markets):\n{headline_element.text.strip()}"
        else:
            text = "❌ Не вдалося знайти заголовки на Bloomberg. (Можливо, клас заголовка змінився)."
        
        await message.answer(text)
        
    except requests.exceptions.RequestException as req_err:
        await message.answer(f"❌ Помилка мережі при доступі до Bloomberg: {req_err}")
    except Exception as e:
        await message.answer(f"❌ Загальна помилка парсингу: {e}")
    # ---------------------------


# --- Web Server для Render (щоб не засинав) ---
# ... (Інший код залишається без змін) ...

async def handle_ping(request):
    """Простий обробник для пінг-запитів Render"""
    return web.Response(text="I'm alive and ready to work!")

async def start_web_server():
    """Запускає веб-сервер на порту, який очікує Render (PORT)"""
    # Render передає порт через змінну оточення PORT
    port = int(os.environ.get("PORT", 8080)) 
    app = web.Application()
    app.router.add_get('/', handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"✅ Web server started on port {port}")

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