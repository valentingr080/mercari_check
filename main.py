# main.py
import time
import threading
from selenium import webdriver
from typing import Optional
import os

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

from config import (
    HEADLESS, WAIT_SECONDS,
    TELEGRAM_TOKEN, CHAT_ID,
    CHECK_INTERVAL, OTHERS_INTERVAL, JDIRECT_INTERVAL, SURUGAYA_INTERVAL,
    CURRENCY_RATES, JDIRECT_PROXY
)

from notifier.telegram import TelegramNotifier
from storage.seen_store import SeenStore

from scrapers.mercari import MercariScraper
from scrapers.fril import FrilScraper
from scrapers.yahoo import YahooAuctionsScraper
from scrapers.surugaya import SurugayaAvailabilityScraper
from scrapers.surugaya2 import SurugayaAvailabilityScraper2
from scrapers.inazuma_shopify import InazumaShopifyScraper
from scrapers.jdirectauctions import JDirectAuctionsScraper  # <-- NEW


def init_driver(proxy: Optional[str] = None):
    opts = Options()

    if HEADLESS:
        # "new" is fine on modern Chrome; if it ever causes issues, switch to "--headless"
        opts.add_argument("--headless=new")

    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("start-maximized")

    opts.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
    )

    if proxy:
        opts.add_argument(f"--proxy-server=http://{proxy}")

    # ✅ Preferred: Selenium Manager (Selenium >= 4.6)
    # This avoids webdriver_manager and usually fixes arch issues automatically.
    #
    # ✅ Optional fallback: if you set CHROMEDRIVER=/path/to/chromedriver,
    # it will use that.
    chromedriver_path = os.environ.get("CHROMEDRIVER")
    if chromedriver_path:
        service = Service(chromedriver_path)
        return webdriver.Chrome(service=service, options=opts)

    # Selenium Manager path (no Service passed)
    return webdriver.Chrome(options=opts)

def format_message(source: str, product):
    title = ""
    if product.extra and isinstance(product.extra, dict):
        title = product.extra.get("title", "")

    if source == "surugaya":
        return f"✅ Producto disponible en Surugaya\n{product.url}"

    msg = f"Nuevo producto 🚨 ({source})\n"
    if title:
        msg += f"{title}\n"
    msg += f"{source}: {product.url}"

    if product.price:
        msg += f"\nPrecio: {product.price}"

    if source == "mercari":
        doorzo_hex = product.url.encode("utf-8").hex()
        doorzo_url = f"https://www.doorzo.com/es/mall/mercari/detail/{doorzo_hex}"
        msg += f"\nDoorzo: {doorzo_url}"

    return msg


def notify_new(scraper, store: SeenStore, notifier: TelegramNotifier):
    source = scraper.source
    products = scraper.fetch()
    found = 0

    for p in products:
        if store.has(p.id):
            continue
        store.add(p.id)

        msg = format_message(source, p)

        try:
            if p.image and source in ("yahoo", "jdirectauctions"):
                notifier.send_photo(p.image, caption=msg)
            else:
                notifier.send_message(msg)
        except Exception as e:
            print(f"[ERROR] Telegram send failed ({source}) for {p.id}: {e}")
            # fallback to text so you still get notified
            try:
                notifier.send_message(msg)
            except Exception as e2:
                print(f"[ERROR] Fallback send_message failed ({source}) for {p.id}: {e2}")


        print("[NOTIF]", msg)
        found += 1

    if found == 0:
        print(f"[INFO] Sin novedades en {source}.")


# -------- threading helpers --------

class LockedStore:
    """Wrap SeenStore with a lock so has/add is atomic across threads."""
    def __init__(self, store: SeenStore, lock: threading.Lock):
        self.store = store
        self.lock = lock

    def has(self, key: str) -> bool:
        with self.lock:
            return self.store.has(key)

    def add(self, key: str) -> None:
        with self.lock:
            self.store.add(key)


class LockedNotifier:
    """Serialize Telegram sends so threads don't step on each other."""
    def __init__(self, notifier: TelegramNotifier, lock: threading.Lock):
        self.notifier = notifier
        self.lock = lock

    def send_message(self, text: str):
        with self.lock:
            return self.notifier.send_message(text)

    def send_photo(self, photo_url: str, caption: str = ""):
        with self.lock:
            return self.notifier.send_photo(photo_url, caption=caption)


def scraper_worker(name: str, scraper, store, notifier, interval: float, stop_event: threading.Event):
    """
    Runs notify_new(scraper, store, notifier) forever every `interval` seconds.
    Uses stop_event so we can exit cleanly.
    """
    print(f"[THREAD] Started: {name} (interval={interval})")
    while not stop_event.is_set():
        start = time.time()
        try:
            notify_new(scraper, store, notifier)
        except Exception as e:
            print(f"[ERROR] {name}: {e}")

        # sleep remaining time, but wake early if stop_event is set
        elapsed = time.time() - start
        remaining = max(0.0, interval - elapsed)
        stop_event.wait(remaining)

    print(f"[THREAD] Stopped: {name}")


def main():
    # shared locks
    notifier_lock = threading.Lock()
    store_lock = threading.Lock()

    base_notifier = TelegramNotifier(TELEGRAM_TOKEN, CHAT_ID)
    notifier = LockedNotifier(base_notifier, notifier_lock)

    stop_event = threading.Event()

    # drivers: IMPORTANT → do not share the same driver across threads
    driver_m1 = init_driver()
    driver_m2 = init_driver()
    driver_fril = init_driver()
    driver_yahoo = init_driver()
    driver_sur = init_driver()
    # driver_jdirect = init_driver(proxy=JDIRECT_PROXY)
    driver_jdirect = init_driver()

    # stores (wrapped with lock)
    stores = {
        "mercari_1": LockedStore(SeenStore("seen_products_mercari_1.txt"), store_lock),
        "mercari_2": LockedStore(SeenStore("seen_products_mercari_2.txt"), store_lock),
        "fril": LockedStore(SeenStore("seen_products_fril.txt"), store_lock),
        "yahoo": LockedStore(SeenStore("seen_products_yahoo.txt"), store_lock),
        "surugaya": LockedStore(SeenStore("seen_products_surugaya_available.txt"), store_lock),
        "inazuma_shopify": LockedStore(SeenStore("seen_products_inazuma_shopify.txt"), store_lock),
        "jdirectauctions": LockedStore(SeenStore("seen_products_jdirectauctions.txt"), store_lock),  # <-- NEW
    }

    # scrapers
    mercari_1 = MercariScraper(
        driver_m1,
        "https://jp.mercari.com/search?keyword=%20%E3%82%A4%E3%83%8A%E3%82%BA%E3%83%9E%E3%82%A4%E3%83%AC%E3%83%96%E3%83%B3&order=desc&sort=created_time",
        currency_rates=CURRENCY_RATES,
        wait_seconds=WAIT_SECONDS,
    )
    mercari_2 = MercariScraper(
        driver_m2,
        "https://jp.mercari.com/search?keyword=%20%E3%82%A4%E3%83%8A%E3%82%BA%E3%83%9E%E3%82%A4%E3%83%AC%E3%83%B1TCG&order=desc&sort=created_time",
        currency_rates=CURRENCY_RATES,
        wait_seconds=WAIT_SECONDS,
    )
    fril = FrilScraper(
        driver_fril,
        "https://fril.jp/s?order=desc&query=%E3%82%A4%E3%83%8A%E3%82%BA%E3%83%9E%E3%82%A4%E3%83%AC%E3%83%96%E3%83%B3&sort=created_at",
        wait_seconds=WAIT_SECONDS,
    )
    yahoo = YahooAuctionsScraper(
        driver_yahoo,
        "https://auctions.yahoo.co.jp/search/search?p=%E3%82%A4%E3%83%8A%E3%82%BA%E3%83%9E%E3%82%A4%E3%83%AC%E3%83%96%E3%83%B3&va=%E3%82%A4%E3%83%8A%E3%82%BA%E3%83%9E%E3%82%A4%E3%83%AC%E3%83%96%E3%83%B3&is_postage_mode=1&dest_pref_code=13&b=1&n=50&s1=new&o1=d",
        wait_seconds=WAIT_SECONDS,
    )
    surugaya = SurugayaAvailabilityScraper2(
        driver_sur,
        ids_file="surugaya_ids.txt",
        wait_seconds=WAIT_SECONDS,
    )
    inazuma_shopify = InazumaShopifyScraper(
        "https://inazuma-eleven-oficial.myshopify.com/collections/all?page=1",
        max_pages=10,
    )

    jdirect = JDirectAuctionsScraper(
        driver_jdirect,
        "https://auctions.yahoo.co.jp/search/search?p=%E3%82%A4%E3%83%8A%E3%82%BA%E3%83%9E%E3%82%A4%E3%83%AC%E3%83%96%E3%83%B3&va=%E3%82%A4%E3%83%8A%E3%82%BA%E3%83%9E%E3%82%A4%E3%83%AC%E3%83%96%E3%83%B3&is_postage_mode=1&dest_pref_code=13&b=1&n=50&s1=new&o1=d",
    )

    threads = [
        threading.Thread(
            target=scraper_worker,
            args=("mercari_1", mercari_1, stores["mercari_1"], notifier, CHECK_INTERVAL, stop_event),
            daemon=True,
        ),
        threading.Thread(
            target=scraper_worker,
            args=("mercari_2", mercari_2, stores["mercari_2"], notifier, CHECK_INTERVAL, stop_event),
            daemon=True,
        ),
        threading.Thread(
            target=scraper_worker,
            args=("fril", fril, stores["fril"], notifier, OTHERS_INTERVAL, stop_event),
            daemon=True,
        ),
        # threading.Thread(
        #     target=scraper_worker,
        #     args=("yahoo", yahoo, stores["yahoo"], notifier, OTHERS_INTERVAL, stop_event),
        #     daemon=True,
        # ),
        # threading.Thread(
        #     target=scraper_worker,
        #     args=("jdirectauctions", jdirect, stores["jdirectauctions"], notifier, JDIRECT_INTERVAL, stop_event),
        #     daemon=True,
        # ),
        threading.Thread(
            target=scraper_worker,
            args=("surugaya", surugaya, stores["surugaya"], notifier, SURUGAYA_INTERVAL, stop_event),
            daemon=True,
        ),
        threading.Thread(
            target=scraper_worker,
            args=("inazuma_shopify", inazuma_shopify, stores["inazuma_shopify"], notifier, OTHERS_INTERVAL, stop_event),
            daemon=True,
        ),
    ]

    for t in threads:
        t.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[MAIN] Stopping...")
        stop_event.set()
        for t in threads:
            t.join(timeout=10)
    finally:
        for d in (driver_m1, driver_m2, driver_fril, driver_yahoo, driver_sur, driver_jdirect):
            try:
                d.quit()
            except Exception:
                pass


if __name__ == "__main__":
    main()
