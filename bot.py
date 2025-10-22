import os
import re
import asyncio
import logging
from typing import List, Dict, Tuple
from urllib.parse import urljoin, urlsplit, urlunsplit, parse_qsl, urlencode

import aiohttp
from aiohttp import web
from bs4 import BeautifulSoup, Tag

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

# -------------------- ЛОГИ --------------------
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
log = logging.getLogger("news-bot")

# -------------------- ENV ---------------------
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
WEBHOOK_BASE = os.environ.get("WEBHOOK_URL")  # напр. https://universal-bot-live.onrender.com

if not BOT_TOKEN or not WEBHOOK_BASE:
    raise RuntimeError("BOT_TOKEN і WEBHOOK_URL обов'язкові в Environment.")

WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"{WEBHOOK_BASE}{WEBHOOK_PATH}"

# -------------------- BOT/DP -------------------
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

# ================== УТИЛІТИ ===================

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
)

HEADERS = {"User-Agent": USER_AGENT, "Accept-Language": "en,*;q=0.5"}

TITLE_MIN = 40  # мін. довжина заголовку, щоб відсікти рубрики/меню

def clean_url(u: str) -> str:
    """Прибрати трекінг-параметри типу utm_*, at_*, fbclid тощо."""
    try:
        parts = urlsplit(u)
        if not parts.scheme:
            # бувають протоколи типу //domain/path
            if parts.netloc:
                u = "https:" + u
                parts = urlsplit(u)
        q = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
             if not (k.startswith("utm_") or k.startswith("at_") or k in {"fbclid", "gclid"})]
        new_query = urlencode(q)
        return urlunsplit((parts.scheme, parts.netloc, parts.path, new_query, parts.fragment))
    except Exception:
        return u

def norm_space(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()

def long_enough(title: str) -> bool:
    return len(norm_space(title)) >= TITLE_MIN

def is_menu_context(tag: Tag) -> bool:
    """Ігноруємо посилання з меню/футера/сайдбарів."""
    for p in tag.parents:
        if not isinstance(p, Tag):
            continue
        name = p.name or ""
        cls = " ".join(p.get("class", [])).lower()
        if name in {"nav", "footer", "header", "aside"}:
            return True
        if any(k in cls for k in ("menu", "nav", "footer", "header", "subscribe", "newsletter")):
            return True
    return False

def has_time_or_summary(article: Tag) -> bool:
    if not isinstance(article, Tag):
        return False
    if article.find("time"):
        return True
    # будь-який короткий опис під заголовком
    for d in article.find_all(["p", "div"]):
        txt = norm_space(d.get_text(" ", strip=True))
        if 40 <= len(txt) <= 300:
            return True
    return False

def dedup(items: List[Dict]) -> List[Dict]:
    seen: set[Tuple[str, str]] = set()
    out = []
    for it in items:
        key = (it.get("source", ""), norm_space(it.get("title", "")).lower())
        url_key = clean_url(it.get("link", ""))
        if key in seen or url_key in {x.get("link") for x in out}:
            continue
        seen.add(key)
        it["link"] = url_key
        out.append(it)
    return out

def chunk_text(lines: List[str], limit: int = 3900) -> List[str]:
    """Розбити список рядків на повідомлення для Telegram (до ~4000 символів)."""
    chunks, buf = [], ""
    for line in lines:
        if len(buf) + len(line) + 1 > limit:
            chunks.append(buf)
            buf = ""
        buf += ("" if not buf else "\n") + line
    if buf:
        chunks.append(buf)
    return chunks

# ================== ПАРСЕРИ ===================

async def fetch_html(session: aiohttp.ClientSession, url: str) -> str:
    for attempt in range(2):
        try:
            async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=20)) as r:
                r.raise_for_status()
                return await r.text()
        except Exception as e:
            if attempt == 1:
                log.warning(f"Fetch failed {url}: {e}")
            await asyncio.sleep(0.4)
    return ""

# ---- BBC Business ----
BBC_ALLOW_RE = re.compile(r"^https?://(www\.)?bbc\.com/(news/(articles|business(-\d+)?|us-canada|world)|worklife/article/)", re.I)
BBC_BLOCK_RE = re.compile(r"/(live|video|audio|watch-live|newsletters|help|about|usingthebbc|cookies|privacy|contact)", re.I)

async def parse_bbc(session) -> List[Dict]:
    url = "https://www.bbc.com/business"
    html = await fetch_html(session, url)
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    items = []
    for art in soup.find_all("article"):
        h = art.find(["h2", "h3"])
        if not h:
            continue
        a = h.find("a", href=True)
        if not a:
            continue
        title = norm_space(a.get_text(" ", strip=True))
        href = a["href"]
        if not href.startswith("http"):
            href = urljoin("https://www.bbc.com", href)
        if is_menu_context(a):
            continue
        if not long_enough(title):
            continue
        if BBC_BLOCK_RE.search(href):
            continue
        if not BBC_ALLOW_RE.search(href):
            continue
        # бажано наявність часу/опису
        if not has_time_or_summary(art):
            # інколи статті без <time> — все одно дозволимо, але фільтр заголовка нас рятує
            pass
        items.append({"title": title, "link": clean_url(href), "source": "BBC (Business)"})
    return items

# ---- Epravda Finances ----
EPR_BLOCK_RE = re.compile(r"/(about|rules|privacy|mediakit|projects|press-release|weeklycharts|land|interview|publications|club|tabloid|champion|eurointegration|istpravda|na-svoii-zemli|zviazok-nezlamnykh)/?", re.I)
EPR_ALLOW_RE = re.compile(r"https?://(www\.)?epravda\.com\.ua/(finances|biznes|power|svit|tehnologiji|news)/[-a-z0-9]+-\d+/?", re.I)

async def parse_epravda_finances(session) -> List[Dict]:
    url = "https://www.epravda.com.ua/finances/"
    html = await fetch_html(session, url)
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    items = []
    for art in soup.find_all("article"):
        h = art.find(["h2", "h3"])
        if not h:
            continue
        a = h.find("a", href=True)
        if not a:
            continue
        title = norm_space(a.get_text(" ", strip=True))
        href = a["href"]
        if not href.startswith("http"):
            href = urljoin("https://www.epravda.com.ua", href)
        if is_menu_context(a):
            continue
        if EPR_BLOCK_RE.search(href):
            continue
        if not EPR_ALLOW_RE.search(href):
            continue
        if not long_enough(title) and not has_time_or_summary(art):
            continue
        items.append({"title": title, "link": clean_url(href), "source": "Epravda (Finances)"})
    return items

# ---- Epravda Columns ----
EPR_COL_ALLOW_RE = re.compile(r"https?://(www\.)?epravda\.com\.ua/(columns|biznes|power|svit|tehnologiji)/[-a-z0-9]+-\d+/?", re.I)

async def parse_epravda_columns(session) -> List[Dict]:
    url = "https://www.epravda.com.ua/columns/"
    html = await fetch_html(session, url)
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    items = []
    for art in soup.find_all("article"):
        h = art.find(["h2", "h3"])
        if not h:
            continue
        a = h.find("a", href=True)
        if not a:
            continue
        title = norm_space(a.get_text(" ", strip=True))
        href = a["href"]
        if not href.startswith("http"):
            href = urljoin("https://www.epravda.com.ua", href)
        if is_menu_context(a):
            continue
        if EPR_BLOCK_RE.search(href):
            continue
        if not EPR_COL_ALLOW_RE.search(href):
            continue
        if not long_enough(title) and not has_time_or_summary(art):
            continue
        items.append({"title": title, "link": clean_url(href), "source": "Epravda (Columns)"})
    return items

# ---- Reuters (generic for 3 розділи) ----
REUTERS_ALLOW_RE = re.compile(r"^https?://(www\.)?reuters\.com/(business|markets|technology)/.+/\d{4}-\d{2}-\d{2}/", re.I)
REUTERS_BLOCK_RE = re.compile(r"/(video|pictures|graphics|live|podcasts|events)/", re.I)

async def parse_reuters_section(session, base_url: str, source_name: str) -> List[Dict]:
    html = await fetch_html(session, base_url)
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    items = []
    for art in soup.find_all("article"):
        h = art.find(["h2", "h3"])
        if not h:
            continue
        a = h.find("a", href=True)
        if not a:
            continue
        title = norm_space(a.get_text(" ", strip=True))
        href = a["href"]
        if not href.startswith("http"):
            href = urljoin("https://www.reuters.com", href)
        if is_menu_context(a):
            continue
        if REUTERS_BLOCK_RE.search(href):
            continue
        if not REUTERS_ALLOW_RE.search(href):
            continue
        if not long_enough(title) and not has_time_or_summary(art):
            continue
        items.append({"title": title, "link": clean_url(href), "source": source_name})
    return items

# ---- FT (4 розділи) ----
FT_UUID_RE = re.compile(r"^https?://(www\.)?ft\.com/content/[0-9a-f-]{36}$", re.I)
FT_BLOCK_RE = re.compile(r"/(stream/|video/|newsletters|signup|subscribe|myft|ai-exchange|ep\.ft\.com|banx|cartoons|live)/", re.I)

async def parse_ft_section(session, path: str, source_name: str) -> List[Dict]:
    base = f"https://www.ft.com/{path.strip('/')}"
    html = await fetch_html(session, base)
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    items = []
    # FT часто кладе статті в article або card-блоки; збираємо заголовки h2/h3 з <a>
    for h in soup.find_all(["h2", "h3"]):
        a = h.find("a", href=True)
        if not a:
            continue
        if is_menu_context(a):
            continue
        title = norm_space(a.get_text(" ", strip=True))
        href = a["href"]
        if not href.startswith("http"):
            href = urljoin("https://www.ft.com", href)
        if FT_BLOCK_RE.search(href):
            continue
        # найкращий сигнал — UUID у /content/...
        if not (FT_UUID_RE.match(href) or "/content/" in href):
            continue
        if not long_enough(title):
            # якщо дуже схоже на секцію — відсікаємо
            continue
        items.append({"title": title, "link": clean_url(href), "source": source_name})
    return items

# =============== АГРЕГАТОР /news ===============

SOURCES = [
    ("BBC", parse_bbc),
    ("EpravdaFin", parse_epravda_finances),
    ("EpravdaCol", parse_epravda_columns),
    ("ReutersBiz", lambda s: parse_reuters_section(s, "https://www.reuters.com/business", "Reuters (Business)")),
    ("ReutersMkt", lambda s: parse_reuters_section(s, "https://www.reuters.com/markets", "Reuters (Markets)")),
    ("ReutersTech", lambda s: parse_reuters_section(s, "https://www.reuters.com/technology", "Reuters (Technology)")),
    ("FTCompanies", lambda s: parse_ft_section(s, "companies", "FT (Companies)")),
    ("FTTech",     lambda s: parse_ft_section(s, "technology", "FT (Technology)")),
    ("FTMarkets",  lambda s: parse_ft_section(s, "markets", "FT (Markets)")),
    ("FTOpinion",  lambda s: parse_ft_section(s, "opinion", "FT (Opinion)")),
]

async def gather_news() -> List[Dict]:
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        tasks = [fn(session) for _, fn in SOURCES]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    all_items: List[Dict] = []
    for name, res in zip([n for n, _ in SOURCES], results):
        if isinstance(res, Exception):
            log.warning(f"{name} failed: {res}")
            continue
        all_items.extend(res or [])
    # де-дуп і легке сортування: FT/Reuters/BBC/Epravda за алфавітом джерела
    all_items = dedup(all_items)
    all_items.sort(key=lambda x: x.get("source", "") + x.get("title", ""))
    return all_items

def render_lines(items: List[Dict]) -> List[str]:
    lines = []
    for it in items:
        t = norm_space(it["title"])
        l = it["link"]
        s = it["source"]
        # без прев’ю: даємо просту кулю, назву і лінк
        lines.append(f"• {t} ({l}) ({s})")
    return lines

# ================== ХЕНДЛЕРИ ==================

@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "👋 Привіт! Надішли /news — отримаєш актуальні новини з 10 джерел (живий парсинг).\n"
        "Також є /ping для перевірки звʼязку."
    )

@dp.message(Command("ping"))
async def cmd_ping(message: Message):
    await message.answer("🏓 Pong")

@dp.message(Command("news"))
async def cmd_news(message: Message):
    try:
        note = "⏳ Збираю актуальні новини прямо зараз… (10 джерел)"
        await message.answer(note, disable_web_page_preview=True)
        items = await gather_news()
        if not items:
            await message.answer("⚠️ Не вдалося отримати новини. Спробуй ще раз за хвилину.")
            return
        lines = render_lines(items)
        chunks = chunk_text(lines, 3800)
        await message.answer("📰 Актуальні новини (живий парсинг)", disable_web_page_preview=True)
        for c in chunks:
            await message.answer(c, disable_web_page_preview=True)
        await message.answer(f"✅ Надіслано: {len(items)} новин з 10 джерел.")
    except Exception as e:
        log.exception("news failed")
        await message.answer("❌ Помилка під час збору новин. Спробуй ще раз трохи пізніше.")

# ================== AIOHTTP СЕРВЕР =============

async def handle_health(request):
    return web.Response(text="OK", status=200)

async def on_startup(app: web.Application):
    log.info(f"🌐 Starting bot, setting webhook to {WEBHOOK_URL}")
    await bot.set_webhook(WEBHOOK_URL)
    log.info("✅ Webhook set successfully")

async def on_shutdown(app: web.Application):
    log.info("🔻 Deleting webhook & closing session…")
    await bot.delete_webhook()
    await bot.session.close()
    log.info("✅ Shutdown complete")

def main():
    app = web.Application()
    # Реєстрація вебхука
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)

    # Healthchecks
    app.router.add_get("/", handle_health)
    app.router.add_get("/healthz", handle_health)

    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)

    port = int(os.environ.get("PORT", "10000"))
    log.info(f"🚀 Starting web server on 0.0.0.0:{port}")
    web.run_app(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    main()