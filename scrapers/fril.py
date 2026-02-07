# scrapers/fril.py
from __future__ import annotations
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, StaleElementReferenceException

from scrapers.base import Scraper, Product


class FrilScraper(Scraper):
    source = "fril"

    def __init__(self, driver, url: str, jpy_to_eur: float = 0.0062, wait_seconds: int = 15):
        self.driver = driver
        self.url = url
        self.jpy_to_eur = jpy_to_eur
        self.wait_seconds = wait_seconds

    def fetch(self) -> list[Product]:
        self.driver.get(self.url)

        try:
            wait = WebDriverWait(self.driver, self.wait_seconds)
            wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "section.view.view_grid")))
        except Exception:
            pass

        try:
            section = self.driver.find_element(By.CSS_SELECTOR, "section.view.view_grid")
            links = section.find_elements(By.CSS_SELECTOR, "a[href*='item.fril.jp']")
        except (StaleElementReferenceException, NoSuchElementException):
            links = []

        products: list[Product] = []
        for a in links:
            href = a.get_attribute("href")
            pid = href.rstrip("/").split("/")[-1]

            try:
                price_block = a.find_element(By.XPATH, ".//p[contains(@class,'item-box__item-price')]")
                currency = price_block.find_element(By.XPATH, ".//span[1]").text.strip()
                number = price_block.find_element(By.XPATH, ".//span[2]").text.strip().replace(",", "")
                eur = round(int(number) * self.jpy_to_eur, 2)
                price_text = f"{number}{currency} (~{eur} €)"
            except Exception:
                price_text = "desconocido"

            products.append(Product(id=pid, url=href, price=price_text))

        return products
