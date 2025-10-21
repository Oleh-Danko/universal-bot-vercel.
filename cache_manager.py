import feedparser
import json
import logging
import os
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

# === КОНФІГУРАЦІЯ ===
logger = logging.getLogger(__name__)

# МАКСИМАЛЬНА КІЛЬКІСТЬ СТАТЕЙ НА ДЖЕРЕЛО (ЗБІЛЬШЕНО З 50 ДО 100)
# Це дозволить нам завантажити 10 джерел * 100 статей = 1000 спроб, 
# що має дати 300+ реально корисних новин.
ARTICLE_LIMIT_PER_SOURCE = 100 

# Файл для збереження кешу
CACHE_FILE = 'news_cache.json'

# Джерела RSS (10 джерел)
RSS_SOURCES = {
    # BBC (UKRAINE - Ua/Ru - high volume, but often duplicates/low quality)
    "BBC News Ukraine": "https://www.bbc.com/ukrainian/rss.xml",
    
    # Economics/Finance (High Quality, often English, key for business context)
    "Економічна правда": "https://www.epravda.com.ua/rss/",
    "Financial Times": "https://www.ft.com/?format=rss",
    "Reuters Top News": "https://www.reuters.com/rssfeed/in/topnews", 
    "The Guardian (World)": "https://www.theguardian.com/world/rss",
    
    # General/World News (Medium volume, good quality)
    "Sky News": "http://feeds.skynews.com/feeds/rss/home.xml",
    "Al Jazeera": "https://www.aljazeera.com/xml/rss/all.xml",
    "DW (English)": "https://rss.dw.com/xml/rss-en-all",
    
    # Tech/Business
    "TechCrunch": "https://techcrunch.com/feed/",
    
    # Mix
    "Укрінформ (Top)": "https://www.ukrinform.ua/rss",
}


# === КЛАС ДЛЯ УПРАВЛІННЯ КЕШЕМ ===
class CacheManager:
    def __init__(self):
        self._cache = self._load_from_file()

    def _load_from_file(self):
        """Завантажує кеш з файлу, якщо він існує."""
        if os.path.exists(CACHE_FILE):
            try:
                with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    logger.info(f"Cache loaded from file. Articles count: {len(data.get('articles', []))}")
                    return data
            except (IOError, json.JSONDecodeError) as e:
                logger.error(f"Error loading cache file: {e}. Starting with empty cache.")
                return {}
        return {}

    def save_cache(self, data):
        """Зберігає кеш у файл."""
        try:
            with open(CACHE_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            self._cache = data
            logger.info(f"Cache saved successfully. Articles count: {len(data['articles'])}")
        except IOError as e:
            logger.error(f"Error saving cache file: {e}")

    def load_cache(self):
        """Повертає поточний кеш (читання з пам'яті)."""
        return self._cache or self._load_from_file()


# === ФУНКЦІЇ ПАРСИНГУ ===
def parse_source(source_name, rss_url):
    """Парсить один RSS-потік та повертає список статей."""
    logger.info(f"Parsing {source_name}...")
    articles = []
    
    try:
        # Встановлюємо таймаут 10 секунд
        feed = feedparser.parse(rss_url, timeout=10)
    except Exception as e:
        logger.error(f"Error parsing {source_name} ({rss_url}): {e}")
        return []

    # ЛІМІТ ЗБІЛЬШЕНО ДО ARTICLE_LIMIT_PER_SOURCE (100)
    for entry in feed.entries[:ARTICLE_LIMIT_PER_SOURCE]:
        try:
            # Обов'язкові поля
            title = entry.get('title')
            link = entry.get('link')
            
            # Фільтруємо неповні статті
            if not title or not link:
                continue

            article = {
                'title': title.strip(),
                'link': link.strip(),
                'source': source_name,
                # 'published': entry.get('published_parsed') # Не використовуємо datetime object тут
            }
            articles.append(article)
        except Exception as e:
            logger.warning(f"Skipping article from {source_name} due to error: {e}")
    
    logger.info(f"Finished parsing {source_name}. Found {len(articles)} articles.")
    return articles


def run_cache_update():
    """Виконує паралельний парсинг усіх джерел та оновлює кеш."""
    logger.info("Starting global cache update...")
    
    all_articles = []
    
    # Використовуємо ThreadPoolExecutor для паралельного парсингу
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = []
        for name, url in RSS_SOURCES.items():
            futures.append(executor.submit(parse_source, name, url))
        
        # Збираємо результати
        for future in futures:
            try:
                articles = future.result()
                all_articles.extend(articles)
            except Exception as e:
                logger.error(f"Error collecting results from a parser thread: {e}")
    
    # Видалення дублікатів на основі посилання (link)
    unique_links = set()
    final_articles = []
    
    # Сортування перед видаленням дублікатів (за джерелом, наприклад)
    all_articles.sort(key=lambda x: x['source'])
    
    for article in all_articles:
        if article['link'] not in unique_links:
            unique_links.add(article['link'])
            final_articles.append(article)
            
    # Фінальне сортування: найновіші статті (хоча RSS зазвичай вже відсортовані за новизною)
    # Залишаємо сортування за джерелом для кращого відображення в боті
    # final_articles.sort(key=lambda x: x.get('published', ''), reverse=True)
    
    # Оновлення кешу
    cache_manager = CacheManager()
    new_cache_data = {
        'timestamp': datetime.now().isoformat(),
        'articles': final_articles
    }
    
    cache_manager.save_cache(new_cache_data)
    logger.info(f"Global cache update finished. Total unique articles saved: {len(final_articles)}")
    return len(final_articles)