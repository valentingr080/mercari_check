from playwright.sync_api import sync_playwright

def get_dpop():
    target = "https://api.mercari.jp/v2/entities:search"
    search_url = "https://jp.mercari.com/search?keyword=%20%E3%82%A4%E3%83%8A%E3%82%BA%E3%83%9E%E3%82%A4%E3%83%AC%E3%83%96%E3%83%B3&order=desc&sort=created_time"

    with sync_playwright() as p:
        browser = p.webkit.launch(headless=True)
        page = browser.new_page()

        with page.expect_request(lambda r: target in r.url, timeout=100000) as req_info:
            page.goto(search_url)

        request = req_info.value
        headers = request.all_headers()
        dpop = headers.get("dpop")

        browser.close()
        return dpop
