import requests

from config.settings import settings


class TelegramBot:
    """
    Sends completed race analysis reports to Telegram.
    """

    def __init__(self):
        self.token = settings.TELEGRAM_BOT_TOKEN
        self.chat_id = settings.TELEGRAM_CHAT_ID

    def is_configured(self):
        return bool(self.token and self.chat_id)

    def send_message(self, message):
        """
        Send a plain-text message to the configured Telegram chat.
        """

        if not self.is_configured():
            print(
                "Telegram is not configured. "
                "Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID."
            )
            return False

        url = f"https://api.telegram.org/bot{self.token}/sendMessage"

        payload = {
            "chat_id": self.chat_id,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }

        try:
            response = requests.post(
                url,
                json=payload,
                timeout=30,
            )

            response.raise_for_status()

            data = response.json()

            if not data.get("ok"):
                print(f"Telegram API error: {data}")
                return False

            print("Telegram message sent successfully.")
            return True

        except requests.RequestException as error:
            print(f"Failed to send Telegram message: {error}")
            return False


telegram_bot = TelegramBot()
