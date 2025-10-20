import requests
from bs4 import BeautifulSoup
import logging

logger = logging.getLogger("BloombergParser")

# Налаштування заголовків для імітації браузера
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

def fetch_bloomberg_news() -> list[dict]:
    """
    Парсить головну сторінку Bloomberg для отримання останніх новин.
    Використовує requests та BeautifulSoup.
    """
    url = "https://www.bloomberg.com"
    
    try:
        # Виконання HTTP-запиту
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status() # Викликає помилку для поганих відповідей (4xx або 5xx)

        # Парсинг HTML-вмісту
        soup = BeautifulSoup(response.text, 'html.parser')

        # Знаходимо всі посилання, які містять заголовок
        # Bloomberg часто використовує тег <a> з класом 'headline' або 'story-card'
        # Шукаємо елементи, які, ймовірно, є посиланнями на статті
        articles = soup.select('a.headline, a[data-component="StoryCardHeadline"]')
        
        news_items = []
        for article in articles:
            title_text = article.text.strip()
            link_url = article.get('href')

            # Перевірка на валідність даних
            if title_text and link_url:
                # Bloomberg може повертати відносні URL. Робимо їх абсолютними.
                if not link_url.startswith('http'):
                    link_url = f"{url}{link_url}"
                
                news_items.append({
                    'title': title_text,
                    'link': link_url
                })
                
        logger.info(f"Successfully scraped {len(news_items)} items from Bloomberg.")
        return news_items

    except requests.exceptions.RequestException as req_err:
        logger.error(f"Request error for Bloomberg: {req_err}")
    except Exception as e:
        logger.error(f"General error during Bloomberg scraping: {e}")
    
    return []