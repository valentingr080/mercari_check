# main.py
import time
import threading
from typing import Optional, Dict, Callable, Tuple
import os
import platform
import requests

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

from config import (
    HEADLESS, WAIT_SECONDS,
    TELEGRAM_TOKEN, CHAT_ID,
    CHECK_INTERVAL, OTHERS_INTERVAL, JDIRECT_INTERVAL, SURUGAYA_INTERVAL,
    CURRENCY_RATES, JDIRECT_PROXY, SHOP_CONFIG_URL
)

from notifier.telegram import TelegramNotifier
from storage.seen_store import SeenStore

from scrapers.mercari import MercariScraper
from scrapers.fril import FrilScraper
from scrapers.yahoo import YahooAuctionsScraper
from scrapers.surugaya2 import SurugayaAvailabilityScraper2
from scrapers.inazuma_shopify import InazumaShopifyScraper
from scrapers.jdirectauctions import JDirectAuctionsScraper
from scrapers.mercari_api import MercariApiScraper
from scrapers.jdirect_fleamarket_api import JDirectFleamarketApiScraper


# ---------------- webdriver ----------------

def init_driver(proxy: Optional[str] = None):
    opts = Options()

    if HEADLESS:
        opts.add_argument("--headless=new")
        opts.add_argument("--window-size=1920,1080")

    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--disable-blink-features=AutomationControlled")

    if platform.system().lower() == "linux":
        opts.binary_location = "/usr/bin/google-chrome"

    if proxy:
        if "://" not in proxy:
            proxy = "http://" + proxy
        opts.add_argument(f"--proxy-server={proxy}")

    return webdriver.Chrome(options=opts)


# ---------------- formatting + notify ----------------

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

    if source == "mercari" or source == "mercari_api":
        doorzo_hex = product.url.encode("utf-8").hex()
        doorzo_url = f"https://www.doorzo.com/es/mall/mercari/detail/{doorzo_hex}"
        msg += f"\nDoorzo: {doorzo_url}"

    return msg


def notify_new(scraper, store, notifier):
    source = scraper.source
    products = scraper.fetch()
    found = 0

    for p in products:
        if store.has(p.id):
            continue
        store.add(p.id)

        msg = format_message(source, p)

        try:
            if p.image:
                notifier.send_photo_download(p.image, caption=msg)
            else:
                notifier.send_message(msg)
        except Exception as e:
            print(f"[ERROR] Telegram send failed ({source}) for {p.id}: {e}")
            try:
                notifier.send_message(msg)
            except Exception as e2:
                print(f"[ERROR] Fallback send_message failed ({source}) for {p.id}: {e2}")

        print("[NOTIF]", msg)
        found += 1

    if found == 0:
        print(f"[INFO] Sin novedades en {source}.")


# ---------------- threading helpers ----------------

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

    def send_photo_download(self, photo_url: str, caption: str = ""):
        with self.lock:
            return self.notifier.send_photo_download(photo_url, caption=caption)


def scraper_worker(name: str, scraper, store, notifier, interval: float, stop_event: threading.Event):
    print(f"[THREAD] Started: {name} (interval={interval})")
    while not stop_event.is_set():
        start = time.time()
        try:
            notify_new(scraper, store, notifier)
        except Exception as e:
            print(f"[ERROR] {name}: {e}")

        elapsed = time.time() - start
        remaining = max(0.0, interval - elapsed)
        stop_event.wait(remaining)

    print(f"[THREAD] Stopped: {name}")


# ---------------- dynamic config loader ----------------

def parse_yes_no_config(text: str) -> Dict[str, bool]:
    """
    Supports lines like:
      mercari_api: Yes
      fleamarket_api: No
    Ignores blank lines and # comments.
    """
    flags: Dict[str, bool] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        key = k.strip()
        val = v.strip().lower()
        flags[key] = val in ("yes", "true", "1", "on", "y")
    return flags


def load_shop_flags() -> Dict[str, bool]:
    if SHOP_CONFIG_URL:
        try:
            r = requests.get(SHOP_CONFIG_URL, timeout=15)
            r.raise_for_status()
            return parse_yes_no_config(r.text)
        except Exception as e:
            print(f"[WARN] Failed to fetch SHOP_CONFIG_URL: {e}")
            return {}
    else:
        path = os.getenv("SHOP_CONFIG_FILE", "shops_config.txt")
        try:
            with open(path, "r", encoding="utf-8") as f:
                return parse_yes_no_config(f.read())
        except FileNotFoundError:
            print(f"[WARN] Local config not found: {path}")
            return {}
        except Exception as e:
            print(f"[WARN] Failed to read local config: {e}")
            return {}


# ---------------- main ----------------

def main():
    # shared locks
    notifier_lock = threading.Lock()
    store_lock = threading.Lock()

    base_notifier = TelegramNotifier(TELEGRAM_TOKEN, CHAT_ID)
    notifier = LockedNotifier(base_notifier, notifier_lock)

    # main stop (kills scheduler + any running workers)
    global_stop = threading.Event()

    # --- stores (locked) ---
    stores = {
        "mercari_1": LockedStore(SeenStore("seen_products_mercari_1.txt"), store_lock),
        "fril": LockedStore(SeenStore("seen_products_fril.txt"), store_lock),
        "yahoo": LockedStore(SeenStore("seen_products_yahoo.txt"), store_lock),
        "surugaya": LockedStore(SeenStore("seen_products_surugaya_available.txt"), store_lock),
        "inazuma_shopify": LockedStore(SeenStore("seen_products_inazuma_shopify.txt"), store_lock),
        "jdirectauctions": LockedStore(SeenStore("seen_products_jdirectauctions.txt"), store_lock),
        "mercari_api": LockedStore(SeenStore("seen_products_mercari_api.txt"), store_lock),
        "fleamarket_api": LockedStore(SeenStore("seen_products_fleamarket_api.txt"), store_lock),
    }

    # Track drivers we create so we can quit safely
    drivers = []

    # --- factories ---
    # Each entry returns (scraper_instance, interval_seconds).
    # IMPORTANT: create drivers inside factories so each scraper gets its own driver.
    def make_mercari_api():
        return (MercariApiScraper(
            "イナズマイレブン",
            currency_rates=CURRENCY_RATES,
            page_size=10,
            max_pages=1,
        ), CHECK_INTERVAL)

    def make_fleamarket_api():
        return (JDirectFleamarketApiScraper(
            "イナズマイレブン",
            currency_rates=CURRENCY_RATES
        ), OTHERS_INTERVAL)

    def make_fril():
        d = init_driver()
        drivers.append(d)
        return ( FrilScraper(
            d,
            "https://fril.jp/s?order=desc&query=%E3%82%A4%E3%83%8A%E3%82%BA%E3%83%9E%E3%82%A4%E3%83%AC%E3%83%96%E3%83%B3&sort=created_at",
            wait_seconds=WAIT_SECONDS,
        ), OTHERS_INTERVAL)
    
    def make_mercari_1():
        d = init_driver()
        drivers.append(d)
        return ( MercariScraper(
            d,
            "https://jp.mercari.com/search?keyword=%20%E3%82%A4%E3%83%8A%E3%82%BA%E3%83%9E%E3%82%A4%E3%83%AC%E3%83%96%E3%83%B3&order=desc&sort=created_time",
            currency_rates=CURRENCY_RATES,
            wait_seconds=WAIT_SECONDS,
        ), CHECK_INTERVAL )

    def make_yahoo():
        d = init_driver()
        drivers.append(d)
        return ( YahooAuctionsScraper(
            d,
            "https://auctions.yahoo.co.jp/search/search?p=%E3%82%A4%E3%83%8A%E3%82%BA%E3%83%9E%E3%82%A4%E3%83%AC%E3%83%96%E3%83%B3&va=%E3%82%A4%E3%83%8A%E3%82%BA%E3%83%9E%E3%82%A4%E3%83%AC%E3%83%96%E3%83%B3&is_postage_mode=1&dest_pref_code=13&b=1&n=50&s1=new&o1=d",
            wait_seconds=WAIT_SECONDS,
        ), OTHERS_INTERVAL )
    
    def make_surugaya():
        d = init_driver()
        drivers.append(d)
        return ( SurugayaAvailabilityScraper2(
            d,
            ids_file="surugaya_ids.txt",
            wait_seconds=WAIT_SECONDS,
        ), SURUGAYA_INTERVAL )
    
    def make_shopify():
        return ( InazumaShopifyScraper(
            "https://inazuma-eleven-oficial.myshopify.com/collections/all?page=1",
            max_pages=10,
        ), OTHERS_INTERVAL )
    
    def make_jdirect():
        d = init_driver()
        drivers.append(d)
        return ( JDirectAuctionsScraper(
            d,
            "https://auctions.yahoo.co.jp/search/search?p=%E3%82%A4%E3%83%8A%E3%82%BA%E3%83%9E%E3%82%A4%E3%83%AC%E3%83%96%E3%83%B3&va=%E3%82%A4%E3%83%8A%E3%82%BA%E3%83%9E%E3%82%A4%E3%83%AC%E3%83%96%E3%83%B3&is_postage_mode=1&dest_pref_code=13&b=1&n=50&s1=new&o1=d",
        ), OTHERS_INTERVAL)
    
    SCRAPER_FACTORIES: Dict[str, Callable[[], Tuple[object, float]]] = {
        "mercari_api": make_mercari_api,
        "fleamarket_api": make_fleamarket_api,
        "fril": make_fril,
        "mercari_1": make_mercari_1,
        "yahoo": make_yahoo,
        "surugaya": make_surugaya,
        "inazuma_shopify": make_shopify,
        "jdirectauctions": make_jdirect
    }

    # --- dynamic worker registry ---
    running: Dict[str, Dict[str, object]] = {}
    registry_lock = threading.Lock()

    def start_worker(name: str):
        if name not in SCRAPER_FACTORIES:
            print(f"[WARN] No factory for shop '{name}', ignoring.")
            return
        scraper, interval = SCRAPER_FACTORIES[name]()
        stop_event = threading.Event()
        t = threading.Thread(
            target=scraper_worker,
            args=(name, scraper, stores[name], notifier, interval, stop_event),
            daemon=True,
        )
        t.start()
        running[name] = {"thread": t, "stop": stop_event}
        print(f"[MAIN] Enabled shop: {name}")

    def stop_worker(name: str):
        info = running.get(name)
        if not info:
            return
        info["stop"].set()
        info["thread"].join(timeout=10)
        running.pop(name, None)
        print(f"[MAIN] Disabled shop: {name}")

    def reconcile_enabled_shops(flags: Dict[str, bool]):
        desired = {k for k, v in flags.items() if v}
        with registry_lock:
            current = set(running.keys())

            # stop those no longer desired
            for name in sorted(current - desired):
                stop_worker(name)

            # start new ones
            for name in sorted(desired - current):
                start_worker(name)

    # Scheduler loop: refresh config every 5 minutes
    def scheduler_loop():
        print("[SCHED] Dynamic shop scheduler started (refresh=300s)")
        while not global_stop.is_set():
            try:
                flags = load_shop_flags()
                # If file is empty or failed, do nothing (keep current state)
                if flags:
                    reconcile_enabled_shops(flags)
                else:
                    print("[SCHED] No flags loaded (empty or fetch error). Keeping current state.")
            except Exception as e:
                print(f"[SCHED] Error: {e}")

            global_stop.wait(300)  # 5 minutes
        print("[SCHED] Scheduler stopped")

    scheduler_thread = threading.Thread(target=scheduler_loop, daemon=True)
    scheduler_thread.start()

    # Optional: start immediately with current config (so you don't wait 5 min)
    initial_flags = load_shop_flags()
    if initial_flags:
        reconcile_enabled_shops(initial_flags)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[MAIN] Stopping...")
        global_stop.set()

        with registry_lock:
            for name in list(running.keys()):
                stop_worker(name)

        scheduler_thread.join(timeout=5)

    finally:
        # Quit drivers safely (only those we actually created)
        for d in drivers:
            try:
                d.quit()
            except Exception:
                pass


if __name__ == "__main__":
    main()
