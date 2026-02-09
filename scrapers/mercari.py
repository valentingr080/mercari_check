# scrapers/mercari.py
from __future__ import annotations
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from scrapers.base import Scraper, Product


class MercariScraper(Scraper):
    source = "mercari"

    def __init__(self, driver, url: str, currency_rates: dict, wait_seconds: int = 15):
        self.driver = driver
        self.url = url
        self.currency_rates = currency_rates
        self.wait_seconds = wait_seconds

    def _trigger_search_again(self) -> None:
        wait = WebDriverWait(self.driver, 10)
        btn = wait.until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "div[data-testid='search-submit-button'] button")
            )
        )
        self.driver.execute_script("arguments[0].click();", btn)

    def fetch(self) -> list[Product]:
        if self.driver.current_url != self.url:
            self.driver.get(self.url)

        self._trigger_search_again()

        items = self.driver.find_elements(By.CSS_SELECTOR, "li[data-testid='item-cell']")
        products: list[Product] = []

        for li in items:
            try:
                a = li.find_element(By.CSS_SELECTOR, "a[href*='/item/']")
                href = a.get_attribute("href")
                pid = href.rstrip("/").split("/")[-1]

                name = li.find_element( By.CSS_SELECTOR, "span[data-testid='thumbnail-item-name']").text.strip()
                upper_name = name.upper()
                if "3DS" in upper_name or "DS" in upper_name:
                    continue

                price_block = li.find_element(By.CSS_SELECTOR, "span.merPrice")
                currency = price_block.find_element(By.CSS_SELECTOR, "span[class^='currency']").text.strip()
                number = price_block.find_element(By.CSS_SELECTOR, "span[class^='number']").text.strip().replace(",", "")
                amount = float(number)

                if currency in self.currency_rates:
                    eur = round(amount * self.currency_rates[currency], 2)
                    price_text = f"{eur} €"
                else:
                    price_text = f"{amount} {currency} (sin conversión)"

                products.append(Product(id=pid, url=href, price=price_text))
            except Exception:
                continue

        # unique by id
        uniq = {p.id: p for p in products}
        return list(uniq.values())
