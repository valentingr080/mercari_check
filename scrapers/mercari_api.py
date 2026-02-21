# scrapers/mercari_api.py
from __future__ import annotations
from utils.dpop import get_dpop

import os
import requests
from typing import Optional, Any

from scrapers.base import Scraper, Product


class MercariApiScraper(Scraper):
    source = "mercari_api"
    API_URL = "https://api.mercari.jp/v2/entities:search"

    def __init__(
        self,
        keyword: str,
        *,
        currency_rates: dict,
        page_size: int = 10,
        max_pages: int = 1,
        wait_seconds: int = 20,
    ):
        self.keyword = keyword
        self.currency_rates = currency_rates
        self.page_size = page_size
        self.max_pages = max_pages
        self.timeout_seconds = wait_seconds
        self.session = requests.Session()
        self._dpop: Optional[str] = None

    def _headers(self) -> dict:
        if not self._dpop:
            self._dpop = get_dpop()

        return {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "ja",
            "Content-Type": "application/json",
            "Origin": "https://jp.mercari.com",
            "Referer": "https://jp.mercari.com/",
            "User-Agent": "Mozilla/5.0",
            "X-Country-Code": "JP",
            "X-Platform": "web",
            "Dpop": self._dpop,
        }

    def fetch(self) -> list[Product]:
        products: list[Product] = []

        for _ in range(self.max_pages):
            payload = {
                "userId": "",
                "pageSize": self.page_size,
                "pageToken": "",
                "searchSessionId": "fedb5b64163acdfb7cb2130e32c9edff",
                "indexRouting": "INDEX_ROUTING_UNSPECIFIED",
                "laplaceDeviceUuid": "d2ef04fd4236346966d14723d9962ad1",
                "serviceFrom": "suruga",
                "source": "BaseSerp",
                "useDynamicAttribute": True,
                "withAuction": True,
                "withItemBrand": True,
                "withItemPromotions": True,
                "withItemSize": False,
                "withItemSizes": True,
                "withOfferPricePromotion": True,
                "withParentProducts": False,
                "withProductArticles": True,
                "withProductSuggest": True,
                "withSearchConditionId": False,
                "withShopname": False,
                "withSuggestedItems": True,
                "thumbnailTypes": [],
                "config": {"responseToggles": ["QUERY_SUGGESTION_WEB_1"]},
                "searchCondition": {
                    "keyword": self.keyword,
                    "excludeKeyword": "",
                    "sort": "SORT_CREATED_TIME",
                    "order": "ORDER_DESC",
                    "status": [],
                },
            }

            resp = self.session.post(
                    self.API_URL,
                    json=payload,
                    headers=self._headers(),
                    timeout=self.timeout_seconds,
            )

            # If failed → refresh DPoP and retry once
            if resp.status_code != 200:
                print(f"DPoP likely expired. Refreshing... ({resp.status_code})")

                self._dpop = get_dpop()  # refresh token

                resp = self.session.post(
                    self.API_URL,
                    json=payload,
                    headers=self._headers(),
                    timeout=self.timeout_seconds,
                )

                if resp.status_code != 200:
                    raise RuntimeError( f"Mercari API error {resp.status_code}: {resp.text[:300]}" )


            data: dict[str, Any] = resp.json()
            items = data.get("items", [])

            for item in items:
                item_id = item.get("id")
                name = (item.get("name") or "").strip()
                upper_name = name.upper()
                if "3DS" in upper_name or "DS" in upper_name:
                    continue
                
                price = item.get("price")

                if not item_id or not name or price is None:
                    continue

                if item_id.startswith("m"):
                    url = f"https://jp.mercari.com/item/{item_id}"
                else:
                    url = f"https://jp.mercari.com/shops/product/{item_id}"

                products.append(
                    Product(
                        id=item_id,
                        price=int(price),
                        url=url,
                    )
                )
            page_token = data.get("nextPageToken") or ""
            if not page_token:
                break

        return products
