from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field


class NoticeItem(BaseModel):
    id: str
    title: Optional[str] = None
    description: Optional[str] = None
    procurement_url: Optional[str] = None
    notice_url: Optional[str] = None
    country_code: str
    publication_date: Optional[date] = None
    deadline: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class NoticeListResponse(BaseModel):
    items: list[NoticeItem]
    page: int = Field(ge=1)
    per_page: int = Field(ge=1, le=100)
    total: int = Field(ge=0)
