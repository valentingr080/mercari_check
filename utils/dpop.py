from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError

def get_dpop():
    target = "https://api.mercari.jp/v2/entities:search"
    search_url = "https://jp.mercari.com/search?keyword=%20%E3%82%A4%E3%83%8A%E3%82%BA%E3%83%9E%E3%82%A4%E3%83%AC%E3%83%96%E3%83%B3&order=desc&sort=created_time"

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
        )
        context = browser.new_context()
        page = context.new_page()

        # reduce load / memory
        page.route(
            "**/*",
            lambda route: route.abort()
            if route.request.resource_type in ("image", "font", "media")
            else route.continue_()
        )

        try:
            # Don’t rely on default 30s
            page.goto(search_url, wait_until="domcontentloaded", timeout=90_000)

            # Now wait for the API call you care about
            with page.expect_request(lambda r: target in r.url, timeout=90_000) as req_info:
                # Trigger something if needed; often just being on the page is enough,
                # but sometimes scrolling helps:
                page.mouse.wheel(0, 1500)

            req = req_info.value
            dpop = req.all_headers().get("dpop")
            return dpop

        except PWTimeoutError as e:
            print("Timed out:", e)
            return None

        finally:
            context.close()
            browser.close()
