# notifier/telegram.py
import requests
import io
import requests

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

    def send_photo_download(self, photo_url: str, caption: str = ""):
        tg_url = f"https://api.telegram.org/bot{self.token}/sendPhoto"

        try:
            img_resp = requests.get(
                photo_url,
                headers={
                    "User-Agent": "Mozilla/5.0",
                    "Referer": "https://paypayfleamarket.yahoo.co.jp/",
                    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
                },
                timeout=self.timeout,
                stream=True,
            )
            img_resp.raise_for_status()
            img_bytes = img_resp.content

        except Exception as e:
            print("[TELEGRAM][sendPhotoUpload] PHOTO_URL:", photo_url)
            print("[TELEGRAM][sendPhotoUpload] download failed:", repr(e))
            raise RuntimeError(f"Failed to download photo for Telegram upload: {e}") from e

        data = {"chat_id": self.chat_id}
        if caption:
            data["caption"] = caption[:1024]

        content_type = img_resp.headers.get("Content-Type", "image/jpeg")
        ext = "jpg"
        if "png" in content_type:
            ext = "png"
        elif "webp" in content_type:
            ext = "webp"
        elif "gif" in content_type:
            ext = "gif"

        files = {
            "photo": (f"photo.{ext}", io.BytesIO(img_bytes), content_type)
        }

        r = requests.post(tg_url, data=data, files=files, timeout=self.timeout)

        try:
            resp_data = r.json()
        except Exception:
            resp_data = {"ok": False, "description": f"Non-JSON response: {r.text[:500]}"}

        if not r.ok or not resp_data.get("ok"):
            print("[TELEGRAM][sendPhotoUpload] PHOTO_URL:", photo_url)
            print("[TELEGRAM][sendPhotoUpload] HTTP:", r.status_code)
            print("[TELEGRAM][sendPhotoUpload] RESP:", r.text[:1000])
            raise RuntimeError(f"Telegram sendPhoto(upload) failed: {resp_data}")

        return resp_data

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