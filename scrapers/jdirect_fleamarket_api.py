# scrapers/jdirect_fleamarket_api.py
from __future__ import annotations

import requests
from typing import Any

from scrapers.base import Scraper, Product


class JDirectFleamarketApiScraper(Scraper):
    source = "jdirect_fleamarket_api"
    API_URL = "https://paypayfleamarket.yahoo.co.jp/api/v1/search"
    ITEM_URL_FMT = "https://paypayfleamarket.yahoo.co.jp/item/{item_id}"

    def __init__(
        self,
        keyword: str,
        *,
        currency_rates: dict,
        wait_seconds: int = 20,
    ):
        self.keyword = keyword
        self.currency_rates = currency_rates
        self.timeout_seconds = wait_seconds
        self.session = requests.Session()

    def _headers(self) -> dict:
        return {
            "Accept": "application/json, text/plain, */*",
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://paypayfleamarket.yahoo.co.jp/",
        }

    def fetch(self) -> list[Product]:
        params = {
            # fixed values (like in browser request)
            "results": 10,
            "imageShape": "square",
            "sort": "openTime",
            "order": "DESC",
            "webp": "false",
            "query": self.keyword,
            "queryTarget": ":8",
            "module": "catalog:hit:21",
            "rewriteQueryType": "WAND",
        }

        resp = self.session.get(
            self.API_URL,
            params=params,
            headers=self._headers(),
            timeout=self.timeout_seconds,
        )

        if resp.status_code != 200:
            raise RuntimeError(
                f"JDirectFleamarket API error {resp.status_code}: {resp.text[:300]}"
            )

        data: dict[str, Any] = resp.json()
        items = data.get("items") or []

        products: list[Product] = []

        for item in items:
            item_id = item.get("id")
            price = item.get("price")
            image_url = item.get("thumbnailImageUrl")

            if not item_id or price is None:
                continue

            products.append(
                Product(
                    id=str(item_id),
                    price=int(price),
                    url=self.ITEM_URL_FMT.format(item_id=item_id),
                    image=image_url,
                )
            )

        return products
