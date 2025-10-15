import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from playwright.sync_api import sync_playwright
import logging
from typing import List

logging.basicConfig(level=logging.INFO)

# 🔑 Твій токен
TOKEN = "8392167879:AAG9GgPCXrajvdZca5vJcYopk3HO5w2hBhE"

bot = Bot(token=TOKEN)
dp = Dispatcher()

# 🌍 ІНОЗЕМНІ ДЖЕРЕЛА (ОЧИЩЕНИЙ СПИСОК: видалено Bloomberg, який блокує)
FOREIGN_FEEDS = [
    "https://www.reuters.com/business/",
    "https://www.nytimes.com/international/section/business",
    "https://www.cnbc.com/markets/",
    "https://techcrunch.com/",
    # Додаємо більш стійкі загальні джерела
    "https://www.bbc.com/business",
    "https://edition.cnn.com/business",
]

# 🇺🇦 УКРАЇНСЬКІ ДЖЕРЕЛА (Без змін, оскільки вони не блокують)
UKRAINIAN_FEEDS = [
    "https://forbes.ua/",
    "https://www.liga.net/ua",
    "https://epravda.com.ua/",
    "https://delo.ua/",
    "https://mind.ua/",
    "https://ain.ua/",
    "https://thepage.ua/news",
]

def get_news_sync(sites: List[str]) -> List[str]:
    """Синхронно парсить заголовки новин з вебсайтів (Playwright)."""
    results = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True) 
        page = browser.new_page()

        for site in sites:
            try:
                page.goto(site, timeout=30000) # Таймаут 30 секунд
                page.wait_for_timeout(2000) 
                
                # Ми шукаємо заголовки h2, h3. Якщо на сайті їх немає, ми отримуємо порожній список.
                titles = page.locator("h2, h3").all_text_contents()
                clean = [t.strip() for t in titles if 25 < len(t.strip()) < 120]
                
                if clean:
                    results.append(f"🌐 *{site}*")
                    for t in clean[:3]:
                        # Додаємо посилання на сайт, як ти просив
                        results.append(f"• [{t}]({site})") 
                        
                    results.append("") 
            except Exception as e:
                # Це повідомлення ти побачиш у логах на хостингу, якщо сайт заблокує IP хостингу
                logging.warning(f"⚠️ Блок або помилка на {site}: {e}")
                
        browser.close()
    return results

@dp.message(Command("start"))
async def start_command(message: types.Message):
    await message.answer(
        "👋 Привіт! Я Універсальний бот (на хостингу Render).\n\n"
        "🗞 Використай команди:\n"
        "`/news` — міжнародні новини 🌍 (повільно)\n"
        "`/newsua` — українські новини 🇺🇦 (повільно)",
        parse_mode="Markdown"
    )

@dp.message(Command("news"))
async def send_foreign_news(message: types.Message):
    sent = await message.answer("⏳ Збираю міжнародні новини... Будь ласка, зачекай.")
    news = await asyncio.to_thread(get_news_sync, FOREIGN_FEEDS) 
    
    if news:
        full_text = "\n".join(news)
        await sent.edit_text(full_text[:4096], parse_mode="Markdown", disable_web_page_preview=True)
    else:
        await sent.edit_text("Не вдалося отримати новини 😔 (Можливо, сайти блокують IP хостингу).")


@dp.message(Command("newsua"))
async def send_ukrainian_news(message: types.Message):
    sent = await message.answer("⏳ Збираю українські новини... Будь ласка, зачекай.")
    news = await asyncio.to_thread(get_news_sync, UKRAINIAN_FEEDS)
    
    if news:
        full_text = "\n".join(news)
        await sent.edit_text(full_text[:4096], parse_mode="Markdown", disable_web_page_preview=True)
    else:
        await sent.edit_text("Не вдалося отримати новини 😔 (Можливо, сайти блокують IP хостингу).")


async def main():
    print("✅ Універсальний Playwright-бот запущений і чекає команд...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("🛑 Бот зупинено.")