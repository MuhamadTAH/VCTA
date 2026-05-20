from pydantic import BaseModel, Field
from typing import Optional


class VideoJobCreate(BaseModel):
    store_id: int = Field(..., description="Store ID for this job")


class VideoJobResponse(BaseModel):
    id: int
    store_id: int
    status: str
    input_path: str
    output_path: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class VideoJobStatus(BaseModel):
    status: str
    output_path: Optional[str] = None
    error: Optional[str] = None


class NotificationRequest(BaseModel):
    session_id: int
    title: str
    body: str
    phone_number: Optional[str] = None
    use_whatsapp_fallback: bool = False