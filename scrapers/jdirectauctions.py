# scrapers/jdirectauctions.py
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional
import html  # <-- NEW

from bs4 import BeautifulSoup
import json

from scrapers.base import Scraper, Product


@dataclass
class JDirectAuctionsScraper(Scraper):
    source: str = "jdirectauctions"

    def __init__(self, driver, url: str):
        self.driver = driver
        self.url = url

    def fetch(self) -> List[Product]:
        self.driver.get("https://ipinfo.io/json")

        text = self.driver.find_element("tag name", "body").text
        data = json.loads(text)
        if data.get("country") != "JP":
            print("[JDIRECT][IP CHECK FAILED]", self.driver.find_element("tag name", "body").text)

        self.driver.get(self.url)

        soup = BeautifulSoup(self.driver.page_source, "html.parser")
        
        ul = soup.select_one("ul.Products__items")
        if not ul:
            return []

        products: List[Product] = []
        for li in ul.select("li.Product"):
            a = li.select_one("a.Product__imageLink") or li.select_one("a.Product__titleLink")
            if not a:
                continue

            url = (a.get("href") or "").strip()
            url = html.unescape(url)  # <-- NEW
            if not url:
                continue

            auction_id = (a.get("data-auction-id") or "").strip()
            if not auction_id:
                parts = [p for p in url.split("/") if p]
                auction_id = parts[-1] if parts else url

            price_raw = (a.get("data-auction-price") or "").strip()
            price = self._format_price_yen(price_raw) if price_raw else self._extract_visible_price(li)

            img = li.select_one("img.Product__imageData")
            image = (img.get("src") or "").strip() if img else None
            image = html.unescape(image) if image else None  # <-- NEW

            title = (a.get("data-auction-title") or "").strip()
            if not title:
                title_el = li.select_one("a.Product__titleLink")
                title = (title_el.get_text(strip=True) if title_el else "")

            products.append(
                Product(
                    id=auction_id,
                    url=url,
                    price=price or "N/A",
                    image=image or None,
                    extra={"title": title} if title else None,
                )
            )

        return products

    @staticmethod
    def _format_price_yen(value: str) -> str:
        digits = "".join(ch for ch in value if ch.isdigit())
        if not digits:
            return value
        return f"{int(digits):,} yenes"

    @staticmethod
    def _extract_visible_price(li) -> Optional[str]:
        cur = li.select_one("span.Product__priceValue.u-textRed")
        if cur:
            txt = cur.get_text(" ", strip=True)
            return txt if txt else None

        any_price = li.select_one("span.Product__priceValue")
        if any_price:
            txt = any_price.get_text(" ", strip=True)
            return txt if txt else None

        return None
