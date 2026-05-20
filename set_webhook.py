#!/usr/bin/env python3
"""
set_webhook.py — Register the platform URL with Telegram's Bot API.

Usage:
    python set_webhook.py https://your-ngrok-url.ngrok-free.app
    python set_webhook.py https://your-production-domain.com

Environment variables (optional):
    TELEGRAM_BOT_TOKEN — your bot token (or set in .env)
"""
import sys
import httpx
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.core.config import get_settings


def register_webhook(url: str) -> None:
    settings = get_settings()

    if not settings.TELEGRAM_BOT_TOKEN:
        print("[ERROR] TELEGRAM_BOT_TOKEN is not set. Configure it in .env or environment.")
        sys.exit(1)

    token = settings.TELEGRAM_BOT_TOKEN
    base = f"https://api.telegram.org/bot{token}"

    webhook_url = url.rstrip("/") + "/api/telegram/webhook"
    delete_url = f"{base}/deleteWebhook"

    print(f"[INFO] Registering webhook: {webhook_url}")

    with httpx.Client() as client:
        resp = client.post(
            f"{base}/setWebhook",
            data={"url": webhook_url},
            timeout=10.0,
        )
        data = resp.json()

        if data.get("ok") or data.get("description") == "Webhook was set":
            print("[OK] Webhook registered successfully.")
        else:
            print(f"[WARN] Telegram returned: {data}")

        info_resp = client.get(f"{base}/getWebhookInfo", timeout=10.0)
        info = info_resp.json()
        if info.get("ok"):
            print(f"[INFO] Current webhook info: {info.get('result', {})}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python set_webhook.py <your-platform-url>")
        print("Example: python set_webhook.py https://abc123.ngrok-free.app")
        sys.exit(1)

    register_webhook(sys.argv[1])