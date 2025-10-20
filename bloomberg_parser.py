# ==========================================================
# Файл: bloomberg_parser.py (Заміна)
# Призначення: Заглушка для неробочого парсера Bloomberg.
# Повертає порожній список, щоб не блокувати bot.py.
# ==========================================================

import logging

logger = logging.getLogger("BloombergParser")

def fetch_bloomberg_news() -> list[dict]:
    """
    Повертає порожній список, оскільки парсинг Bloomberg не працює.
    """
    logger.warning("Bloomberg HTML parsing is currently disabled due to instability.")
    return []