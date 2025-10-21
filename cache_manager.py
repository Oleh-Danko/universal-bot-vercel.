import os
import json
import logging
from datetime import datetime
from typing import List, Dict
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger("cache_manager")

CACHE_PATH = "cache/news_cache.json"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36"
}

# === Джерела для збору новин ===
SOURCE_CONFIG = [
    ("Epravda — Finances", "https://www.epravda.com.ua/finances"),
    ("Epravda — Columns", "https://www.epravda.com.ua/columns"),
    ("Reuters — Business", "https://www.reuters.com/business"),
    ("Reuters — Markets", "https://www.reuters.com/markets"),
    ("Reuters — Technology", "https://www.reuters.com/technology"),
    ("FT — Companies", "https://www.ft.com/companies"),
    ("FT — Technology", "https://www.ft.com/technology"),
    ("FT — Markets", "https://www.ft.com/markets"),
    ("FT — Opinion", "https://www.ft.com/opinion"),
    ("BBC — Business", "https://www.bbc.com/business"),
]


def load_cache() -> Dict:
    """Завантаження кешу з файлу."""
    if not os.path.exists(CACHE_PATH):
        return {"timestamp": None, "articles": []}
    try:
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Помилка читання кешу: {e}")
        return {"timestamp": None, "articles": []}


def save_cache(cache: Dict):
    """Збереження кешу."""
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    try:
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Помилка при записі кешу: {e}")


def parse_source(url: str, source_label: str) -> List[Dict[str, str]]:
    """Парсинг однієї сторінки новин."""
    news = []
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # --- Epravda ---
        if "epravda.com.ua" in url:
            for a in soup.select("a.article__title, a.post__title, a.title, h3 a"):
                title = a.get_text(strip=True)
                href = a.get("href")
                if href and title:
                    link = requests.compat.urljoin(url, href)
                    news.append({"title": title, "link": link, "source": source_label})

        # --- Reuters ---
        elif "reuters.com" in url:
            for a in soup.select("a[href^='/']"):
                href = a.get("href")
                title = a.get_text(strip=True)
                if href and title:
                    if any(seg in href for seg in ["/business", "/markets", "/technology"]):
                        link = requests.compat.urljoin("https://www.reuters.com", href)
                        news.append({"title": title, "link": link, "source": source_label})

        # --- Financial Times ---
        elif "ft.com" in url:
            for a in soup.select("a.js-teaser-heading-link, a.o-teaser__heading[href]"):
                title = a.get_text(strip=True)
                href = a.get("href")
                if href and title:
                    link = requests.compat.urljoin("https://www.ft.com", href)
                    news.append({"title": title, "link": link, "source": source_label})

        # --- BBC Business ---
        elif "bbc.com/business" in url:
            for a in soup.select("a.gs-c-promo-heading[href]"):
                title = a.get_text(strip=True)
                href = a.get("href")
                if href and title:
                    link = requests.compat.urljoin("https://www.bbc.com", href)
                    news.append({"title": title, "link": link, "source": source_label})

    except Exception as e:
        logger.error(f"❌ Помилка парсингу {source_label}: {e}")

    return news


def run_cache_update() -> int:
    """Основна функція оновлення кешу з усіх джерел."""
    all_news = []
    seen = set()

    for source_label, url in SOURCE_CONFIG:
        logger.info(f"🔍 Парсинг {source_label}...")
        items = parse_source(url, source_label)
        for item in items:
            if item["link"] not in seen:
                seen.add(item["link"])
                all_news.append(item)

    cache = {
        "timestamp": datetime.utcnow().isoformat(),
        "articles": all_news,
    }

    save_cache(cache)
    logger.info(f"✅ Кеш оновлено ({len(all_news)} новин).")
    return len(all_news)