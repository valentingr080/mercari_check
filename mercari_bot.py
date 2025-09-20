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
from selenium.common.exceptions import NoSuchElementException

# --- CONFIG ---
URL = "https://jp.mercari.com/search?keyword=%20%E3%82%A4%E3%83%8A%E3%82%BA%E3%83%9E%E3%82%A4%E3%83%AC%E3%83%96%E3%83%B3&order=desc&sort=created_time"
SEEN_FILE = "seen_products.txt"
TELEGRAM_TOKEN = "7554414339:AAF4eXm8gRJ7bevSf3b5maXoQUvskSinxnM"
CHAT_ID = "1102153006"
CHECK_INTERVAL = 30
WAIT_SECONDS = 15
HEADLESS = True
CURRENCY_RATES = {
    "¥": 0.0062,   # JPY → EUR
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

    section = driver.find_element(By.CSS_SELECTOR, "section.view.view_grid")
    links = section.find_elements(By.CSS_SELECTOR, "a[href*='item.fril.jp']")
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

def fetch_neokyo(driver):
    URL = "https://neokyo.com/es/search/yahooFleaMarket?provider=yahooFleaMarket&translate=1&order-tag=openTime&order-direction=DESC&keyword=inazuma+eleven"
    JPY_TO_EUR = 0.0062
    driver.get(URL)
    try:
        wait = WebDriverWait(driver, WAIT_SECONDS)
        wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.products-listing")))
    except:
        pass

    product_cards = driver.find_elements(By.CSS_SELECTOR, "div.product-card")
    products = []

    for card in product_cards:
        # Get the link from the 'a' tag within the current product card.
        try:
            a_tag = card.find_element(By.CSS_SELECTOR, "a.product-link")
            href = a_tag.get_attribute("href")
            # Extract the product ID from the URL.
            pid = href.rstrip("/").split("/")[-1]

            # --- Get the image URL ---
            image_tag = card.find_element(By.CSS_SELECTOR, "img.card-img-top")
            image_url = image_tag.get_attribute("src")
        except NoSuchElementException:
            # Skip if no link is found for the product card.
            continue
        
        # Get the price from the 'h5' tag within the '.buy' div.
        try:
            price_element = card.find_element(By.CSS_SELECTOR, "div[class*='buy'] > h5")
            price_text_raw = price_element.text
            # Clean the text and convert to a number.
            number = int(price_text_raw.split()[0].replace(",", ""))
            eur = round(number * JPY_TO_EUR, 2)
            price_text = f"{number} Yen (~{eur} €)"
        except (NoSuchElementException, IndexError, ValueError):
            price_text = "desconocido"
        
        # Add the collected information to the products list.
        products.append({
            "id": pid,
            "url": href,
            "price": price_text,
            "image": image_url 
        })
        
    return products


def fetch_products(driver):
    driver.get(URL)
    try:
        wait = WebDriverWait(driver, WAIT_SECONDS)
        wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "li[data-testid='item-cell']")))
    except Exception:
        pass

    items = driver.find_elements(By.CSS_SELECTOR, "li[data-testid='item-cell']")
    products = []

    for li in items:
        try:
            a = li.find_element(By.CSS_SELECTOR, "a[href*='/item/']")
            href = a.get_attribute("href")
            pid = href.rstrip("/").split("/")[-1]

            # precio
            price_block = li.find_element(By.CSS_SELECTOR, "span.merPrice")
            currency_el = price_block.find_element(By.CSS_SELECTOR, "span[class^='currency']")
            number_el = price_block.find_element(By.CSS_SELECTOR, "span[class^='number']")
            currency = currency_el.text.strip()
            number = number_el.text.strip().replace(",", "")

            amount = float(number)

            if currency in CURRENCY_RATES:
                eur = round(amount * CURRENCY_RATES[currency], 2)
                price_text = f"{eur} €"
            else:
                # moneda desconocida: no convierte
                price_text = f"{amount} {currency} (sin conversión)"

            products.append({"id": pid, "url": href, "price": price_text})
        except Exception:
            continue
    return products

# --- FILE --- 
def load_seen(file):
    if not os.path.exists(file):
        return set()
    with open(file, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f if line.strip())

def append_seen(file, pid):
    with open(file, "a", encoding="utf-8") as f:
        f.write(pid + "\n")

# --- MAIN ---
def main():
    seen_files = {
        "mercari": "seen_products_mercar.txt",
        "fril": "seen_products_fril.txt",
        "neokyo": "seen_products_neokyo.txt"
    }

    seen = {source: load_seen(file) for source, file in seen_files.items()}

    driver = init_driver()
    try:
        while True:
            all_products = {
                "mercari": fetch_products(driver),
                "fril": fetch_fril(driver),
                "neokyo": fetch_neokyo(driver)
            }

            for source, products in all_products.items():
                found = 0
                for p in products:
                    if p["id"] not in seen[source]:
                        seen[source].add(p["id"])
                        append_seen(seen_files[source], p["id"])
                        msg = f"Nuevo producto 🚨 ({source})\n{p['url']}\nPrecio: {p['price']}"
                        if source == "neokyo" and "image" in p:
                            send_telegram_photo(p["image"], caption=msg)
                        else:
                            send_telegram_message(msg)
                        # send_telegram_message(msg)
                        print("[NOTIF]", msg)
                        found += 1
                if found == 0:
                    print(f"[INFO] Sin nuevos productos en {source}.")
            
            time.sleep(CHECK_INTERVAL)
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
