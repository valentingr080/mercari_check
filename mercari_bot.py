import time
import os
import requests
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, StaleElementReferenceException
from selenium.webdriver.common.keys import Keys
import threading


# --- CONFIG ---
URL = "https://jp.mercari.com/search?keyword=%20%E3%82%A4%E3%83%8A%E3%82%BA%E3%83%9E%E3%82%A4%E3%83%AC%E3%83%96%E3%83%B3&order=desc&sort=created_time"
SEEN_FILE = "seen_products.txt"
TELEGRAM_TOKEN = "7554414339:AAF4eXm8gRJ7bevSf3b5maXoQUvskSinxnM"
CHAT_ID = "1102153006"
CHECK_INTERVAL = 1
OTHERS_INTERVAL = 15
SURUGAYA_INTERVAL = 300   # cada cuánto revisar surugaya (1 hora)
WAIT_SECONDS = 15
HEADLESS = True
CURRENCY_RATES = {
    "¥": 0.0057,   # JPY → EUR
    "€": 1.0,      # EUR → EUR
    "SEK": 0.089,  # SEK → EUR (ejemplo, actualízala según corresponda)
    "USD": 0.93    # USD → EUR (ejemplo)
}

# --- TELEGRAM ---
def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text}
    try:
        requests.post(url, data=payload, timeout=10)
    except Exception as e:
        print("[TG ERROR]", e)

def send_telegram_photo(photo_url, caption=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    payload = {"chat_id": CHAT_ID, "photo": photo_url}
    if caption:
        payload["caption"] = caption
    try:
        requests.post(url, data=payload, timeout=10)
    except Exception as e:
        print("[TG PHOTO ERROR]", e)

# --- SELENIUM ---
def init_driver():
    opts = Options()
    if HEADLESS:
        opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("start-maximized")
    opts.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36")
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=opts)
    return driver

def fetch_fril(driver):
    URL = "https://fril.jp/s?order=desc&query=%E3%82%A4%E3%83%8A%E3%82%BA%E3%83%9E%E3%82%A4%E3%83%AC%E3%83%96%E3%83%B3&sort=created_at"
    JPY_TO_EUR = 0.0062
    driver.get(URL)
    try:
        wait = WebDriverWait(driver, WAIT_SECONDS)
        wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "section.view.view_grid")))
    except:
        pass

    try:
        section = driver.find_element(By.CSS_SELECTOR, "section.view.view_grid")
        links = section.find_elements(By.CSS_SELECTOR, "a[href*='item.fril.jp']")
    except ( StaleElementReferenceException, NoSuchElementException ):
        links = []  # o simplemente continue si estás en un loop
    products = []

    for a in links:
        href = a.get_attribute("href")
        pid = href.rstrip("/").split("/")[-1]

        try:
            price_block = a.find_element(By.XPATH, ".//p[contains(@class,'item-box__item-price')]")
            currency = price_block.find_element(By.XPATH, ".//span[1]").text.strip()
            number = price_block.find_element(By.XPATH, ".//span[2]").text.strip().replace(",", "")
            eur = round(int(number) * JPY_TO_EUR, 2)
            price_text = f"{number}{currency} (~{eur} €)"
        except:
            price_text = "desconocido"

        products.append({"id": pid, "url": href, "price": price_text})
    return products

def fetch_yahoo_auctions(driver):
    URL = "https://auctions.yahoo.co.jp/search/search?p=%E3%82%A4%E3%83%8A%E3%82%BA%E3%83%9E%E3%82%A4%E3%83%AC%E3%83%96%E3%83%B3&va=%E3%82%A4%E3%83%8A%E3%82%BA%E3%83%9E%E3%82%A4%E3%83%AC%E3%83%96%E3%83%B3&is_postage_mode=1&dest_pref_code=13&b=1&n=50&s1=new&o1=d"
    JPY_TO_EUR = 0.0062  # mismo que los demás
    driver.get(URL)

    try:
        wait = WebDriverWait(driver, WAIT_SECONDS)
        wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "ul.Product__items > li.Product")))
    except:
        pass

    items = driver.find_elements(By.CSS_SELECTOR, "ul.Product__items > li.Product")
    products = []

    for li in items:
        try:
            # enlace + id
            a_tag = li.find_element(By.CSS_SELECTOR, "a.Product__imageLink")
            href = a_tag.get_attribute("href")
            pid = a_tag.get_attribute("data-auction-id")

            # imagen
            try:
                img_tag = a_tag.find_element(By.CSS_SELECTOR, "img.Product__imageData")
                image_url = img_tag.get_attribute("src")
            except:
                image_url = None

            # precio de subasta inicial (obligatorio)
            try:
                auction_price_el = li.find_element(By.CSS_SELECTOR, "span.Product__priceValue.u-textRed")
                auction_price_raw = auction_price_el.text.strip().replace("円", "").replace(",", "")
                auction_price_jpy = int(auction_price_raw)
                auction_price_eur = round(auction_price_jpy * JPY_TO_EUR, 2)
                auction_price_text = f"{auction_price_jpy} ¥ (~{auction_price_eur} €)"
            except:
                auction_price_text = "desconocido"

            # precio de compra directa (opcional)
            direct_price_text = None
            try:
                direct_price_el = li.find_element(By.CSS_SELECTOR, "span.Product__priceValue:not(.u-textRed)")
                direct_price_raw = direct_price_el.text.strip().replace("円", "").replace(",", "")
                direct_price_jpy = int(direct_price_raw)
                direct_price_eur = round(direct_price_jpy * JPY_TO_EUR, 2)
                direct_price_text = f"{direct_price_jpy} ¥ (~{direct_price_eur} €)"
            except:
                pass

            # mensaje de precio final
            if direct_price_text:
                price_text = f"Subasta: {auction_price_text}\nCompra directa: {direct_price_text}"
            else:
                price_text = f"Subasta: {auction_price_text}"

            products.append({
                "id": pid,
                "url": href,
                "price": price_text,
                "image": image_url
            })
        except Exception as e:
            print("[Yahoo ERROR]", e)
            continue

    return products


def trigger_search_again(driver):
    wait = WebDriverWait(driver, 10)

    search_button = wait.until(
        EC.presence_of_element_located(
            (By.CSS_SELECTOR, "div[data-testid='search-submit-button'] button")
        )
    )

    driver.execute_script("arguments[0].click();", search_button)
    # driver.execute_script(
    #     "arguments[0].scrollIntoView({block: 'center'});",
    #     search_button
    # )
    # search_button.click()


def wait_for_results_refresh(driver):
    wait = WebDriverWait(driver, WAIT_SECONDS)

    old_items = driver.find_elements(
        By.CSS_SELECTOR, "li[data-testid='item-cell']"
    )

    if old_items:
        wait.until(EC.staleness_of(old_items[0]))

    wait.until(
        EC.presence_of_all_elements_located(
            (By.CSS_SELECTOR, "li[data-testid='item-cell']")
        )
    )


def fetch_products(driver, url):
    products = []

    # Load once
    if driver.current_url != url:
        driver.get(url)

    # Trigger search again without full reload
    trigger_search_again(driver)
    # wait_for_results_refresh(driver)

    items = driver.find_elements(
        By.CSS_SELECTOR, "li[data-testid='item-cell']"
    )

    for li in items:
        try:
            a = li.find_element(By.CSS_SELECTOR, "a[href*='/item/']")
            href = a.get_attribute("href")
            pid = href.rstrip("/").split("/")[-1]

            price_block = li.find_element(By.CSS_SELECTOR, "span.merPrice")
            currency_el = price_block.find_element(
                By.CSS_SELECTOR, "span[class^='currency']"
            )
            number_el = price_block.find_element(
                By.CSS_SELECTOR, "span[class^='number']"
            )

            currency = currency_el.text.strip()
            number = number_el.text.strip().replace(",", "")
            amount = float(number)

            if currency in CURRENCY_RATES:
                eur = round(amount * CURRENCY_RATES[currency], 2)
                price_text = f"{eur} €"
            else:
                price_text = f"{amount} {currency} (sin conversión)"

            products.append({
                "id": pid,
                "url": href,
                "price": price_text
            })
        except Exception:
            continue

    unique = {p["id"]: p for p in products}
    return list(unique.values())


# --- FILE --- 
def load_seen(file):
    if not os.path.exists(file):
        return set()
    with open(file, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f if line.strip())

def append_seen(file, pid):
    with open(file, "a", encoding="utf-8") as f:
        f.write(pid + "\n")

# --- SURUGAYA ---
SURUGAYA_FILE = "surugaya_ids.txt"

def load_surugaya_ids():
    if not os.path.exists(SURUGAYA_FILE):
        print(f"[WARN] No se encontró {SURUGAYA_FILE}, crea el archivo con un ID por línea.")
        return []
    with open(SURUGAYA_FILE, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]

def check_surugaya(driver, ids):
    base_url = "https://neokyo.com/es/product/surugaya/"
    newly_available = []

    for pid in ids:
        url = base_url + pid
        try:
            driver.get(url)
            wait = WebDriverWait(driver, WAIT_SECONDS)
            wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))

            # Comprobar si aparece el texto "Disponible" dentro de un <span class="text-success">
            spans = driver.find_elements(By.CSS_SELECTOR, "span.text-success")
            available = any("Disponible" in s.text for s in spans)

            if available:
                msg = f"✅ Producto disponible en Surugaya\n{url}"
                send_telegram_message(msg)
                print("[SURUGAYA DISPONIBLE]", pid, url)
                newly_available.append(pid)
            # elif not available:
            #     print(f"[SURUGAYA] No disponible: {pid}")
        except Exception as e:
            print(f"[SURUGAYA ERROR] {pid}: {e}")

    return newly_available


def check_new_products_and_send_message(seen, seen_files, source, products):
    found = 0
    for p in products:
        if p["id"] not in seen[source]:
            seen[source].add(p["id"])
            append_seen(seen_files[source], p["id"])

            mercari_url = p["url"]

            msg = (
                f"Nuevo producto 🚨 ({source})\n"
                f"{source}: {mercari_url}\n"
                f"Precio: {p['price']}"
            )

            # Only add Doorzo link for Mercari
            if source == "mercari":
                doorzo_hex = mercari_url.encode("utf-8").hex()
                doorzo_url = f"https://www.doorzo.com/es/mall/mercari/detail/{doorzo_hex}"
                msg += f"\nDoorzo: {doorzo_url}"

            if source == "neokyo" and "image" in p:
                send_telegram_photo(p["image"], caption=msg)
            else:
                send_telegram_message(msg)

            print("[NOTIF]", msg)
            found += 1

    if found == 0:
        print(f"[INFO] Sin nuevos productos en {source}.")


def surugaya_worker(driver, surugaya_ids):
    print("[SURUGAYA] Revisión de stock iniciada...")
    check_surugaya(driver, surugaya_ids)
    print("[SURUGAYA] Revisión finalizada")



# --- MAIN ---
def main():
    seen_files = {
        "mercari": "seen_products_mercar.txt",
        "fril": "seen_products_fril.txt",
        "yahoo": "seen_products_yahoo.txt"
    }

    seen = {source: load_seen(file) for source, file in seen_files.items()}
    surugaya_ids = load_surugaya_ids()

    driver = init_driver()
    driver_surugaya_1 = init_driver()
    driver_surugaya_2 = init_driver()
    last_surugaya_check = 0
    last_others_check = 0
    surugaya_thread = None
    
    try:
        while True:
            check_new_products_and_send_message(seen, seen_files, "mercari", fetch_products(driver_surugaya_1, 
                    "https://jp.mercari.com/search?keyword=%20%E3%82%A4%E3%83%8A%E3%82%BA%E3%83%9E%E3%82%A4%E3%83%AC%E3%83%96%E3%83%B3&order=desc&sort=created_time"
                ) )

            check_new_products_and_send_message(seen, seen_files, "mercari", fetch_products(driver_surugaya_2,
                    "https://jp.mercari.com/search?keyword=%20%E3%82%A4%E3%83%8A%E3%82%BA%E3%83%9E%E3%82%A4%E3%83%AC%E3%83%96%E3%83%B3TCG&order=desc&sort=created_time"
                ) )

            if time.time() - last_others_check >= OTHERS_INTERVAL:
                check_new_products_and_send_message(seen, seen_files, "fril", fetch_fril(driver))
                last_others_check = time.time()

            if time.time() - last_surugaya_check >= SURUGAYA_INTERVAL:
                if surugaya_thread is None or not surugaya_thread.is_alive():
                    surugaya_thread = threading.Thread(
                        target=surugaya_worker,
                        args=(driver, surugaya_ids),
                        daemon=True
                    )
                    surugaya_thread.start()
                    last_surugaya_check = time.time()

            time.sleep(CHECK_INTERVAL)
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
