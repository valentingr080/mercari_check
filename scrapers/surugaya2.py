# scrapers/surugaya2.py
from __future__ import annotations

import os
from typing import Optional

import requests
from bs4 import BeautifulSoup
from notifier.telegram import TelegramNotifier

from scrapers.base import Scraper, Product

from config import ( 
    TELEGRAM_TOKEN, CHAT_ID,
)

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


def fetch_surugaya_stock(
    surugaya_id: str,
    *,
    session: Optional[requests.Session] = None,
    timeout: int = 8,
    user_agent: str = DEFAULT_USER_AGENT,
    proxies: Optional[dict] = None,
) -> Optional[tuple[bool, Optional[str]]]:
    if not surugaya_id:
        return None

    url = f"https://www.suruga-ya.jp/product/detail/{surugaya_id}"
    s = session or requests.Session()

    headers = {
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ja,en-US;q=0.8,en;q=0.7",
        "Connection": "close",
    }

    try:
        resp = s.get(url, headers=headers, timeout=timeout, proxies=proxies)
        resp.raise_for_status()
    except Exception:
        return None

    soup = BeautifulSoup(resp.text, "html.parser")

    span = soup.select_one("span.text-price-detail.price-buy")
    if not span:
        return (False, None)

    text = span.get_text(strip=True)
    return ("税込" in text, text or None)

def get_text(product):
    return f"✅ Producto disponible en Surugaya\n{product.url}"

class SurugayaAvailabilityScraper2(Scraper):
    """
    Checks availability directly on suruga-ya.jp (requests-based),
    but accepts a driver to stay API-compatible with other scrapers.
    """
    source = "surugaya2"

    def __init__( self, driver, ids_file: str, *, wait_seconds: int = 8, user_agent: str = DEFAULT_USER_AGENT, proxies: Optional[dict] = None, ):
        self.driver = driver        # stored but not used (intentionally)
        self.ids_file = ids_file
        self.wait_seconds = wait_seconds
        self.user_agent = user_agent
        self.proxies = proxies
        self._session = requests.Session()

    def _load_ids(self) -> list[str]:
        if not os.path.exists(self.ids_file):
            print(f"[WARN] No se encontró {self.ids_file}, crea el archivo con un ID por línea.")
            return []
        with open(self.ids_file, "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]

    def fetch(self) -> list[Product]:
        notifier = TelegramNotifier(TELEGRAM_TOKEN, CHAT_ID)
        ids = self._load_ids()
        available: list[Product] = []

        for pid in ids:
            try:
                result = fetch_surugaya_stock( pid, session=self._session, timeout=self.wait_seconds, user_agent=self.user_agent, proxies=self.proxies, )
                if not result:
                    continue

                is_available, price_text = result
                if is_available:
                    # available.append(
                    #     Product(
                    #         id=pid,
                    #         url=f"https://www.suruga-ya.jp/product/detail/{pid}",
                    #         price=price_text or "Disponible",
                    #     )
                    # )
                    message = f"✅ Producto disponible en Surugaya\nhttps://www.suruga-ya.jp/product/detail/{pid}"
                    notifier.send_message(message)
                    # notifier.send_strong_alert(message)

            except Exception as e:
                print(f"[SURUGAYA2 ERROR] {pid}: {e}")

        return available
