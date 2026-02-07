# scrapers/surugaya.py
from __future__ import annotations
import os
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from scrapers.base import Scraper, Product


class SurugayaAvailabilityScraper(Scraper):
    source = "surugaya"

    def __init__(self, driver, ids_file: str, wait_seconds: int = 15):
        self.driver = driver
        self.ids_file = ids_file
        self.wait_seconds = wait_seconds

    def _load_ids(self) -> list[str]:
        if not os.path.exists(self.ids_file):
            print(f"[WARN] No se encontró {self.ids_file}, crea el archivo con un ID por línea.")
            return []
        with open(self.ids_file, "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]

    def fetch(self) -> list[Product]:
        base_url = "https://neokyo.com/es/product/surugaya/"
        ids = self._load_ids()
        available: list[Product] = []
        
        for pid in ids:
            url = base_url + pid
            try:
                self.driver.get(url)
                wait = WebDriverWait(self.driver, self.wait_seconds)
                wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))

                spans = self.driver.find_elements(By.CSS_SELECTOR, "span.text-success")
                is_available = any("Disponible" in s.text for s in spans)

                if is_available:
                    available.append(Product(id=pid, url=url, price="Disponible"))
            except Exception as e:
                print(f"[SURUGAYA ERROR] {pid}: {e}")

        return available
