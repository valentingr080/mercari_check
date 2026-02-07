# notifier/telegram.py
import requests
import time

class TelegramNotifier:
    def __init__(self, token: str, chat_id: str, timeout: int = 15):
        self.token = token
        self.chat_id = chat_id
        self.timeout = timeout

    def send_message(self, text: str):
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {"chat_id": self.chat_id, "text": text}

        r = requests.post(url, data=payload, timeout=self.timeout)
        # Always inspect Telegram response
        try:
            data = r.json()
        except Exception:
            data = {"ok": False, "description": f"Non-JSON response: {r.text[:500]}"}

        if not r.ok or not data.get("ok"):
            print("[TELEGRAM][sendMessage] HTTP:", r.status_code)
            print("[TELEGRAM][sendMessage] RESP:", r.text[:1000])
            # raise to make it visible in your worker error handler
            raise RuntimeError(f"Telegram sendMessage failed: {data}")

        return data

    def send_photo(self, photo_url: str, caption: str = ""):
        url = f"https://api.telegram.org/bot{self.token}/sendPhoto"
        payload = {"chat_id": self.chat_id, "photo": photo_url}

        if caption:
            # Telegram caption limit is 1024 chars
            payload["caption"] = caption[:1024]

        r = requests.post(url, data=payload, timeout=self.timeout)

        try:
            data = r.json()
        except Exception:
            data = {"ok": False, "description": f"Non-JSON response: {r.text[:500]}"}

        if not r.ok or not data.get("ok"):
            print("[TELEGRAM][sendPhoto] PHOTO_URL:", photo_url)
            print("[TELEGRAM][sendPhoto] HTTP:", r.status_code)
            print("[TELEGRAM][sendPhoto] RESP:", r.text[:1000])
            raise RuntimeError(f"Telegram sendPhoto failed: {data}")

        return data

    def send_strong_alert(self, text: str):
        r = requests.post(
            "https://api.pushover.net/1/messages.json",
            data={
                "token": "aez4cz4x2qtasyd56c9gpmkyqwoozp",
                "user": "ufcn57kpsvpi16wo9d1rpozha44m58",
                "message": text,
                "priority": 2,
                "retry": 30,
                "expire": 600,
            },
            timeout=15,
        )

        # Parse response
        try:
            data = r.json()
        except Exception:
            data = {"ok": False, "raw": r.text}

        # Debug prints
        print("HTTP:", r.status_code)
        print("Response:", data)

        # Raise on error
        if r.status_code != 200 or data.get("status") != 1:
            raise RuntimeError(f"Pushover failed: {data}")

        return data