# ==========================================================
# Файл: bloomberg_parser.py (РОБОЧА ВЕРСІЯ)
# Призначення: Парсинг новин з Bloomberg (HTML Scraper).
# ==========================================================

import requests
from bs4 import BeautifulSoup
import logging
from datetime import datetime, timezone
import re

logger = logging.getLogger("BloombergParser")

# URL-адреса Bloomberg, яку ми парсимо
BLOOMBERG_URL = "https://www.bloomberg.com/markets/latest"

def fetch_bloomberg_news() -> list[dict]:
    """
    Отримує новини з Bloomberg шляхом парсингу HTML.
    """
    logger.info(f"Починаю парсинг Bloomberg з {BLOOMBERG_URL}")
    articles = []
    
    # Використовуємо заголовки, щоб імітувати реальний браузер і уникнути блокування
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    try:
        response = requests.get(BLOOMBERG_URL, headers=headers, timeout=15)
        response.raise_for_status() 

        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Основний контейнер для статей на сторінці "Markets/Latest"
        # Шукаємо елементи, які містять заголовок і посилання.
        # Bloomberg часто використовує класи, що містять "latest" або "story"
        story_elements = soup.find_all('article', class_=lambda c: c and ('story' in c or 'latest' in c))
        
        if not story_elements:
            # Спроба знайти альтернативні елементи, якщо основний клас змінився
            story_elements = soup.find_all('div', class_=lambda c: c and 'story-list' in c)

        
        for element in story_elements:
            try:
                # Знаходимо заголовок
                title_tag = element.find('a', {'data-component': 'Headline'}) or element.find('h1') or element.find('h2')
                if not title_tag:
                    continue

                title = title_tag.text.strip()
                link = title_tag.get('href')
                
                # Посилання іноді є відносним, робимо його абсолютним
                if link and not link.startswith('http'):
                    link = f"https://www.bloomberg.com{link}"
                    
                # Знаходимо короткий опис (якщо є)
                summary_tag = element.find('div', class_=lambda c: c and 'summary' in c)
                summary = summary_tag.text.strip() if summary_tag else None

                # Bloomberg не завжди надає чітку дату в окремому тезі, 
                # але ми можемо спробувати знайти його в мета-даних або в самому елементі
                pub_date_str = None
                time_tag = element.find('time')
                if time_tag and time_tag.get('datetime'):
                    pub_date_str = time_tag.get('datetime')
                
                # Оскільки Bloomberg публікує багато, ми використовуємо поточний час, якщо дата не знайдена
                if not pub_date_str:
                    pub_date_str = datetime.now(timezone.utc).isoformat()


                if title and link:
                    articles.append({
                        "title": title,
                        "link": link,
                        "summary": summary,
                        "pubDate": pub_date_str,
                        "source": "Bloomberg" # Джерело додається в cache_manager, але тут для повноти
                    })
            except Exception as e:
                # Ігноруємо погано відформатовані елементи
                logger.debug(f"Помилка парсингу елемента Bloomberg: {e}")
                continue

        logger.info(f"✅ Успішно отримано {len(articles)} статей з Bloomberg.")
        return articles

    except requests.exceptions.RequestException as e:
        logger.error(f"Помилка запиту до Bloomberg: {e}")
        return []
    except Exception as e:
        logger.error(f"Непередбачена помилка під час парсингу Bloomberg: {e}")
        return []

# === Кінець bloomberg_parser.py ===