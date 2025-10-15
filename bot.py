    "https://techcrunch.com/",import os
import json
import logging
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup
from telegram import Update

# --- Конфігурація ---
# Токен береться зі змінних оточення Vercel
BOT_TOKEN = os.environ.get("BOT_TOKEN") 
TELEGRAM_URL = f'https://api.telegram.org/bot{BOT_TOKEN}/'

# --- Логіка пошуку новин (та ж, що й раніше) ---
def search_and_format_news(query="українські новини", count=5):
    """Виконує пошук новин Google і форматує їх."""

    params = {'q': query, 'hl': 'uk', 'gl': 'UA', 'ceid': 'UA:uk', 'tbm': 'nws'}
    google_url = f'https://www.google.com/search?{urlencode(params)}'

    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(google_url, headers=headers)
        response.raise_for_status() 

        soup = BeautifulSoup(response.content, 'html.parser')

        # Шукаємо блоки новин
        news_blocks = soup.find_all('div', class_='xUVHie') or soup.find_all('div', class_='SoaQtd') 

        news_list = []

        for block in news_blocks[:count]:
            link_tag = block.find('a', class_='WlydOe')
            title_tag = block.find('div', class_='BNeawe vvV-b')
            source_tag = block.find('div', class_='BNeawe UPmitb')

            if link_tag and title_tag and source_tag:
                title = title_tag.get_text()
                link = link_tag['href']
                source = source_tag.get_text().split(' · ')[0]
                news_list.append(f"*{title}*\nДжерело: {source}\n[Читати далі]({link})\n")

        if not news_list:
             return "Вибачте, не вдалося знайти свіжих новин."

        return "🗞️ **Ось свіжі українські новини:**\n\n" + "\n".join(news_list)

    except requests.exceptions.RequestException as e:
        logging.error(f"Google Request Error: {e}")
        return "Помилка при запиті до Google."
    except Exception as e:
        logging.error(f"Parsing Error: {e}")
        return "Невідома помилка при парсингу."

# --- Функція відповіді Telegram ---
def send_telegram_response(chat_id, text):
    """Відправляє відповідь назад у Telegram API."""
    url = TELEGRAM_URL + 'sendMessage'
    payload = {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': 'Markdown'
    }
    requests.post(url, json=payload)

# --- Основний обробник оновлень ---
def handle_update(update_json):
    """Обробляє вхідний оновлення (Update) від Telegram."""

    # Використовуємо функцію Update.de_json для коректного парсингу
    update = Update.de_json(update_json, None) 

    if update.message and update.message.text:
        text = update.message.text
        chat_id = update.message.chat_id

        response_text = ""

        if text == '/start':
            response_text = "Привіт! Я — універсальний Telegram-бот для новин. Надішліть /news, щоб отримати свіжі заголовки."
        elif text == '/news':
            response_text = search_and_format_news()
        else:
            response_text = "Вибачте, я розумію лише команди /start та /news."

        send_telegram_response(chat_id, response_text)

    return "ok" 

# --- Головна функція для Vercel (Serverless Entry Point) ---
def handler(event, context):
    """
    Основна функція-обробник, яку викликає Vercel при Webhook-запиті.
    """
    if 'body' in event and event['httpMethod'] == 'POST':
        try:
            update_json = json.loads(event['body'])
            handle_update(update_json)
            return {
                'statusCode': 200,
                'body': json.dumps({'status': 'processed'})
            }
        except Exception as e:
            logging.error(f"Помилка обробки оновлення: {e}")
            return {
                'statusCode': 500,
                'body': json.dumps({'error': str(e)})
            }

    # Відповідь на GET-запит (при прямому переході на URL)
    return {
        'statusCode': 200,
        'body': json.dumps({'message': 'Бот очікує Webhook від Telegram.'})
    }
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
