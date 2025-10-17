# bloomberg_parser.py - ПОВНИЙ КОД (КРОК 1)

import requests
from bs4 import BeautifulSoup
import logging
from typing import List, Dict
import os
import re

logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger("bloomberg_parser")

URL = "https://www.bloomberg.com"

def fetch_bloomberg_news() -> List[Dict[str, str]]:
    """
    Отримує HTML-вміст сторінки Bloomberg та парсить 10 новин.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    }
    
    LOG.info("Sending GET request to %s", URL)
    try:
        # 1. Отримання HTML
        response = requests.get(URL, headers=headers, timeout=15)
        response.raise_for_status() # Перевіряє на помилки HTTP
    except requests.exceptions.RequestException as e:
        LOG.error("Error fetching Bloomberg page: %s", e)
        return []

    # 2. Парсинг HTML
    soup = BeautifulSoup(response.text, 'html.parser')
    news_items = []
    seen_links = set()
    
    # 3. ПОШУК ЗА НОВИННИМИ БЛОКАМИ (Bloomberg часто використовує стійкі класи)
    
    # Шаблон 1: h3 або h4 всередині div[data-component]
    for container in soup.select('div[data-component]'):
        # Шукаємо посилання <a>
        a_tag = container.find('a', href=True)
        if a_tag:
            # Шукаємо заголовок (h3 або h4)
            title_tag = a_tag.find(['h3', 'h4'])
            if not title_tag:
                title_tag = container.find(['h3', 'h4'])
            
            title = title_tag.get_text(strip=True) if title_tag else a_tag.get_text(strip=True)
            link = a_tag['href']
            
            # Фільтрація
            if len(news_items) < 10 and title and len(title) > 10 and not title.lower().startswith('watch'):
                full_link = requests.utils.urljoin(URL, link)
                if full_link not in seen_links:
                    news_items.append({"title": title, "link": full_link})
                    seen_links.add(full_link)
                    if len(news_items) >= 10: break
    
    # Шаблон 2: Прямий пошук посилань з класом, що містить "headline" (резервний)
    if len(news_items) < 10:
        for a_tag in soup.find_all('a', class_=re.compile(r'headline', re.IGNORECASE)):
            title = a_tag.get_text(strip=True)
            link = a_tag['href']
            
            if title and len(title) > 10 and not title.lower().startswith('watch'):
                full_link = requests.utils.urljoin(URL, link)
                if full_link not in seen_links:
                    news_items.append({"title": title, "link": full_link})
                    seen_links.add(full_link)
                    if len(news_items) >= 10: break

    # Фінальна обробка та повернення
    final_news = news_items[:10]
    LOG.info("Successfully parsed %d news items.", len(final_news))
    return final_news

if __name__ == '__main__':
    # Тестовий запуск:
    print("--- Bloomberg News ---")
    news = fetch_bloomberg_news()
    for i, item in enumerate(news):
        print(f"{i+1}. {item['title']} ({item['link']})")