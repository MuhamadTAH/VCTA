from typing import Optional
import re
from app.core.config import get_settings


E164_PATTERN = re.compile(r"^\+[1-9]\d{1,14}$")


async def send_whatsapp_message(phone_number: str, message: str) -> bool:
    if not E164_PATTERN.match(phone_number):
        import logging
        logging.warning(f"Invalid phone number format: {phone_number}")
        return False
    """
    Send a WhatsApp message via an automated gateway integration.
    
    In production, this would integrate with:
    - Twilio WhatsApp API
    - Meta Business API
    - A dedicated WhatsApp gateway service
    
    This is a stub implementation that logs the message.
    """
    settings = get_settings()
    
    if not settings.WHATSAPP_GATEWAY_URL:
        return False
    
    try:
        import httpx
        
        payload = {
            "phone": phone_number,
            "message": message,
            "priority": "high"
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                settings.WHATSAPP_GATEWAY_URL,
                json=payload,
                headers={
                    "Authorization": f"Bearer {settings.WHATSAPP_API_KEY}",
                    "Content-Type": "application/json"
                },
                timeout=15.0
            )
            return response.status_code in (200, 201, 202)
    except Exception:
        return False


async def format_arabic_message(arabic_text: str, store_name: str = "") -> str:
    """
    Format Arabic text for WhatsApp delivery.
    Adds store branding and ensures RTL display.
    """
    header = f"📢 {store_name}" if store_name else "📢"
    footer = "\n---\nئەم نامە لە لایەن سیستەمی ڤیدیۆ وەرگێڕدراوە"
    full_message = f"{header}\n\n{arabic_text}\n{footer}"
    return full_message