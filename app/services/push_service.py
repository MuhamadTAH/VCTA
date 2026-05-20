from typing import Optional
from app.core.config import get_settings


async def send_push_notification(endpoint: str, token: str, title: str, body: str) -> bool:
    """
    Send a Web Push notification via a VAPID-capable server.
    Uses Web Push protocol to deliver notification to the browser service worker.
    
    For this implementation, we use a simple HTTP POST to a push service.
    In production, this would integrate with Firebase Cloud Messaging (FCM) 
    or a self-hosted push service like webpush.
    """
    settings = get_settings()
    
    try:
        import httpx
        
        payload = {
            "to": token,
            "notification": {
                "title": title,
                "body": body,
                "icon": "/static/icon.png",
                "click_action": f"{settings.STORE_URL_BASE}/chat"
            }
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                endpoint,
                json=payload,
                headers={
                    "Authorization": f"key={settings.FCM_SERVER_KEY}",
                    "Content-Type": "application/json"
                },
                timeout=10.0
            )
            return response.status_code in (200, 201, 204)
    except Exception as e:
        import logging
        logging.warning(f"Push notification failed: endpoint={endpoint[:50]}..., error={e}")
        return False


async def register_push_subscription(
    session_id: str,
    endpoint: str,
    token: str
) -> bool:
    """
    Store push subscription in the database.
    """
    from app.core.database import get_database

    async with get_database() as db:
        await db.execute(
            "INSERT OR REPLACE INTO push_subscriptions (session_id, endpoint, token) VALUES (?, ?, ?)",
            (session_id, endpoint, token)
        )
        await db.commit()
    return True


async def get_push_subscription(session_id: str) -> dict | None:
    """
    Retrieve push subscription for a session.
    """
    from app.core.database import get_database

    async with get_database() as db:
        cursor = await db.execute(
            "SELECT endpoint, token FROM push_subscriptions WHERE session_id = ?",
            (session_id,)
        )
        row = await cursor.fetchone()
        if row:
            return {"endpoint": row[0], "token": row[1]}
    return None


async def delete_push_subscription(session_id: str) -> bool:
    """
    Remove push subscription when user opts out.
    """
    from app.core.database import get_database

    async with get_database() as db:
        await db.execute(
            "DELETE FROM push_subscriptions WHERE session_id = ?",
            (session_id,)
        )
        await db.commit()
    return True