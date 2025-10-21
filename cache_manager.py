import json
import asyncio
import logging
from datetime import datetime, timezone

from rss_parser import fetch_all_sources

log = logging.getLogger("cache-manager")

CACHE_FILE = "news_cache.json"

class CacheManager:
    def __init__(self, path: str = CACHE_FILE):
        self.path = path

    def load_cache(self) -> dict:
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return {"timestamp": None, "articles": []}
        except Exception as e:
            log.exception("Load cache error: %s", e)
            return {"timestamp": None, "articles": []}

    def save_cache(self, articles: list[dict]):
        data = {
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "articles": articles
        }
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        log.info("Cache saved. Articles: %d", len(articles))

async def run_cache_update() -> None:
    """
    Тягнемо всі джерела паралельно, чистимо, зберігаємо у файл.
    """
    try:
        articles = await fetch_all_sources()
        cm = CacheManager()
        cm.save_cache(articles)
        return None
    except Exception as e:
        log.exception("run_cache_update error: %s", e)
        return None