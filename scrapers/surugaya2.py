# scrapers/surugaya2.py
from __future__ import annotations

import os
from typing import Optional, Tuple
from datetime import datetime

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


def _parse_bool_flag(raw: str, default: bool = True) -> bool:
    if raw is None:
        return default
    v = raw.strip().lower()
    if v in ("true", "1", "yes", "y", "si", "sí"):
        return True
    if v in ("false", "0", "no", "n"):
        return False
    return default


class SurugayaAvailabilityScraper2(Scraper):
    """
    Checks availability directly on suruga-ya.jp (requests-based),
    but accepts a driver to stay API-compatible with other scrapers.
    """
    source = "surugaya2"

    def __init__(
        self,
        driver,
        ids_file: str,
        *,
        wait_seconds: int = 8,
        user_agent: str = DEFAULT_USER_AGENT,
        proxies: Optional[dict] = None,
    ):
        self.driver = driver  # stored but not used (intentionally)
        self.ids_file = ids_file
        self.wait_seconds = wait_seconds
        self.user_agent = user_agent
        self.proxies = proxies
        self._session = requests.Session()

    def _load_ids(self) -> list[Tuple[str, bool]]:
        """
        Each line supports:
          - "ID"                  -> defaults flag=True
          - "ID,true" / "ID,false"
        """
        if not os.path.exists(self.ids_file):
            print(f"[WARN] No se encontró {self.ids_file}, crea el archivo con un ID por línea.")
            return []

        items: list[Tuple[str, bool]] = []
        with open(self.ids_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                if "," in line:
                    pid, flag = line.split(",", 1)
                    pid = pid.strip()
                    send_strong = _parse_bool_flag(flag, default=True)
                else:
                    pid = line
                    send_strong = True

                if pid:
                    items.append((pid, send_strong))

        return items

    def fetch(self) -> list[Product]:
        print(f"[FETCH STARTED] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        notifier = TelegramNotifier(TELEGRAM_TOKEN, CHAT_ID)
        id_items = self._load_ids()
        available: list[Product] = []

        for pid, send_strong in id_items:
            # Build list of IDs to try (alt inherits the same flag)
            pids_to_try = [pid]
            if pid.startswith("G"):
                alt_pid = "B" + pid[1:]
                pids_to_try.append(alt_pid)

            for current_pid in pids_to_try:
                try:
                    result = fetch_surugaya_stock(
                        current_pid,
                        session=self._session,
                        timeout=self.wait_seconds,
                        user_agent=self.user_agent,
                        proxies=self.proxies,
                    )
                    if not result:
                        continue

                    is_available, price_text = result
                    if is_available:
                        message = (
                            f"✅ Producto disponible en Surugaya\n"
                            f"https://www.suruga-ya.jp/product/detail/{current_pid}"
                        )
                        notifier.send_message(message)

                        # Only send strong alert if flag=true
                        if send_strong:
                            notifier.send_strong_alert(message)

                except Exception as e:
                    print(f"[SURUGAYA2 ERROR] {current_pid}: {e}")

        print(f"[FETCH FINISHED] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        return available