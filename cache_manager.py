import json
import asyncio
from datetime import datetime
from rss_parser import fetch_rss_news

CACHE_FILE = "news_cache.json"

class CacheManager:
    def __init__(self):
        self.file = CACHE_FILE

    def load_cache(self):
        try:
            with open(self.file, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return {"timestamp": None, "articles": []}

    def save_cache(self, articles):
        data = {
            "timestamp": datetime.utcnow().isoformat(),
            "articles": articles
        }
        with open(self.file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

async def run_cache_update():
    articles = await fetch_rss_news()
    cm = CacheManager()
    cm.save_cache(articles)