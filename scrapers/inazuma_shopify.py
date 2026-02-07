# scrapers/inazuma_shopify.py
from __future__ import annotations

from typing import Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from scrapers.base import Scraper, Product


class InazumaShopifyScraper(Scraper):
    """
    Scrapes the Shopify collection page:
    https://inazuma-eleven-oficial.myshopify.com/collections/all?page=1

    Returns Product(id, url, price, image)
    """

    def __init__(self, start_url: str, timeout: int = 25, max_pages: int = 10):
        self.start_url = start_url
        self.timeout = timeout
        self.max_pages = max_pages

        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0 Safari/537.36"
                ),
                "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
            }
        )

    @property
    def source(self) -> str:
        return "inazuma_shopify"

    def fetch(self) -> list[Product]:
        products: list[Product] = []
        seen_in_run: set[str] = set()

        # page=1..max_pages until empty
        for page in range(1, self.max_pages + 1):
            page_url = self._with_page(self.start_url, page)
            html = self._get(page_url)
            parsed = self._parse(html)

            if not parsed:
                break

            for p in parsed:
                if p.id in seen_in_run:
                    continue
                seen_in_run.add(p.id)
                products.append(p)

        return products

    # -------- internal helpers --------

    def _get(self, url: str) -> str:
        r = self.session.get(url, timeout=self.timeout)
        r.raise_for_status()
        return r.text

    def _with_page(self, url: str, page: int) -> str:
        # simple/robust: strip existing ?page=... and rebuild
        base = url.split("?")[0]
        return f"{base}?page={page}"

    def _parse(self, html: str) -> list[Product]:
        soup = BeautifulSoup(html, "html.parser")

        # Your structure: #ResultsList -> ul -> li[data-product-id]
        items = soup.select("#ResultsList li[data-product-id]")
        out: list[Product] = []

        for li in items:
            pid = (li.get("data-product-id") or "").strip()
            if not pid:
                continue

            # Product URL (prefer product-card__link)
            a = (
                li.select_one("a.product-card__link")
                or li.select_one('a[ref="cardGalleryLink"]')
                or li.select_one('a[href^="/products/"]')
            )
            href = (a.get("href") or "").strip() if a else ""
            url = urljoin("https://inazuma-eleven-oficial.myshopify.com", href) if href else ""

            # Price
            # Shopify theme uses <product-price> ... <span class="price">€9,99 EUR</span>
            price_el = li.select_one("product-price .price") or li.select_one(".price")
            price = price_el.get_text(strip=True) if price_el else ""

            # Image
            # Best: product-card-link[data-featured-media-url]
            img_url: Optional[str] = None
            pcl = li.select_one("product-card-link[data-featured-media-url]")
            if pcl and pcl.get("data-featured-media-url"):
                img_url = pcl["data-featured-media-url"].strip()

            # Fallback: first img src
            if not img_url:
                img = li.select_one("img.product-media__image") or li.select_one("img")
                if img and img.get("src"):
                    img_url = img["src"].strip()

            if img_url and img_url.startswith("//"):
                img_url = "https:" + img_url

            # Use title for extra (nice to keep, but your message formatter uses only url/price)
            title_el = li.select_one("h3.h4") or li.select_one('[ref="productTitleLink"] p')
            title = title_el.get_text(strip=True) if title_el else ""

            out.append(
                Product(
                    id=pid,
                    url=url,
                    price=price,
                    image=img_url,
                    extra={"title": title} if title else None,
                )
            )

        return out
