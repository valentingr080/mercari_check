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

# --- CONFIG ---
URL = "https://jp.mercari.com/search?keyword=%20%E3%82%A4%E3%83%8A%E3%82%BA%E3%83%9E%E3%82%A4%E3%83%AC%E3%83%96%E3%83%B3&order=desc&sort=created_time"
SEEN_FILE = "seen_products.txt"
TELEGRAM_TOKEN = "7554414339:AAF4eXm8gRJ7bevSf3b5maXoQUvskSinxnM"
CHAT_ID = "1102153006"
CHECK_INTERVAL = 30
WAIT_SECONDS = 15
HEADLESS = True
JPY_TO_EUR = 0.0062  # cambia la tasa según convenga

# --- FILE ---
def load_seen():
    if not os.path.exists(SEEN_FILE):
        return set()
    with open(SEEN_FILE, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f if line.strip())

def append_seen(pid):
    with open(SEEN_FILE, "a", encoding="utf-8") as f:
        f.write(pid + "\n")

# --- TELEGRAM ---
def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text}
    try:
        requests.post(url, data=payload, timeout=10)
    except Exception as e:
        print("[TG ERROR]", e)

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
            price_text = ""

            if currency == "¥":
                yen = int(number)
                eur = round(yen * JPY_TO_EUR, 2)
                price_text = f"{yen}¥ (~{eur} €)"
            elif currency == "€":
                eur = float(number)
                price_text = f"{eur} €"
            else:
                price_text = f"{currency}{number}"

            products.append({"id": pid, "url": href, "price": price_text})
        except Exception:
            continue
    return products

# --- MAIN ---
def main():
    seen = load_seen()
    driver = init_driver()

    try:
        while True:
            products = fetch_products(driver)
            found = 0
            for p in products:
                if p["id"] not in seen:
                    seen.add(p["id"])
                    append_seen(p["id"])
                    msg = f"Nuevo producto 🚨\n{p['url']}\nPrecio: {p['price']}"
                    send_telegram_message(msg)
                    print("[NOTIF]", msg)
                    found += 1
            if found == 0:
                print("[INFO] Sin nuevos productos.")
            time.sleep(CHECK_INTERVAL)
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
