from typing import Optional
from app.core.config import get_settings


async def send_fcm_push(token: str, title: str, body: str, data: Optional[dict] = None) -> bool:
    """
    Send a Firebase Cloud Messaging push notification.
    
    Args:
        token: FCM device registration token
        title: Notification title
        body: Notification body text
        data: Optional custom data payload
    
    Returns:
        True if sent successfully, False otherwise
    """
    settings = get_settings()
    
    if not settings.FCM_SERVER_KEY:
        return False
    
    try:
        import httpx
        
        fcm_payload = {
            "to": token,
            "notification": {
                "title": title,
                "body": body,
                "sound": "default",
                "priority": "high"
            }
        }
        
        if data:
            fcm_payload["data"] = data
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://fcm.googleapis.com/fcm/send",
                json=fcm_payload,
                headers={
                    "Authorization": f"key={settings.FCM_SERVER_KEY}",
                    "Content-Type": "application/json"
                },
                timeout=10.0
            )
            
            if response.status_code == 200:
                result = response.json()
                return result.get("success", 0) > 0
            
            return False
    except Exception as e:
        import logging
        logging.warning(f"FCM push failed: token={token[:20]}..., error={e}")
        return False


async def send_fcm_to_subscription(session_id: int, title: str, body: str) -> bool:
    """
    Send FCM notification to a session's registered push subscription.
    """
    from app.services.push_service import get_push_subscription
    
    subscription = await get_push_subscription(session_id)
    if not subscription:
        return False
    
    return await send_fcm_push(
        token=subscription["token"],
        title=title,
        body=body,
        data={"session_id": str(session_id)}
    )