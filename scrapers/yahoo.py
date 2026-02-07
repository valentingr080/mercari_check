# scrapers/yahoo.py
from __future__ import annotations
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from scrapers.base import Scraper, Product


class YahooAuctionsScraper(Scraper):
    source = "yahoo"

    def __init__(self, driver, url: str, jpy_to_eur: float = 0.0062, wait_seconds: int = 15):
        self.driver = driver
        self.url = url
        self.jpy_to_eur = jpy_to_eur
        self.wait_seconds = wait_seconds

    def fetch(self) -> list[Product]:
        self.driver.get(self.url)

        try:
            wait = WebDriverWait(self.driver, self.wait_seconds)
            wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "ul.Product__items > li.Product")))
        except Exception:
            pass

        items = self.driver.find_elements(By.CSS_SELECTOR, "ul.Product__items > li.Product")
        products: list[Product] = []

        for li in items:
            try:
                a_tag = li.find_element(By.CSS_SELECTOR, "a.Product__imageLink")
                href = a_tag.get_attribute("href")
                pid = a_tag.get_attribute("data-auction-id")

                image_url = None
                try:
                    img_tag = a_tag.find_element(By.CSS_SELECTOR, "img.Product__imageData")
                    image_url = img_tag.get_attribute("src")
                except Exception:
                    pass

                # auction price
                try:
                    auction_el = li.find_element(By.CSS_SELECTOR, "span.Product__priceValue.u-textRed")
                    auction_jpy = int(auction_el.text.strip().replace("円", "").replace(",", ""))
                    auction_eur = round(auction_jpy * self.jpy_to_eur, 2)
                    auction_txt = f"{auction_jpy} ¥ (~{auction_eur} €)"
                except Exception:
                    auction_txt = "desconocido"

                # direct buy optional
                direct_txt = None
                try:
                    direct_el = li.find_element(By.CSS_SELECTOR, "span.Product__priceValue:not(.u-textRed)")
                    direct_jpy = int(direct_el.text.strip().replace("円", "").replace(",", ""))
                    direct_eur = round(direct_jpy * self.jpy_to_eur, 2)
                    direct_txt = f"{direct_jpy} ¥ (~{direct_eur} €)"
                except Exception:
                    pass

                if direct_txt:
                    price_text = f"Subasta: {auction_txt}\nCompra directa: {direct_txt}"
                else:
                    price_text = f"Subasta: {auction_txt}"

                products.append(Product(id=pid, url=href, price=price_text, image=image_url))
            except Exception as e:
                print("[Yahoo ERROR]", e)

        return products
