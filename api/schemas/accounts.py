from pydantic import BaseModel, ConfigDict
from typing import List, Optional

class LinkAccountsRequest(BaseModel):
    parent_tg_id: int
    student_tg_id: int

class StudentProgressResponse(BaseModel):
    tg_id: int
    username: Optional[str] = None
    role: str
    balance_coins: Optional[int] = None
    xp_total: Optional[int] = None
    streak_days: Optional[int] = None

class MonitoringResponse(BaseModel):
    parent_tg_id: int
    students: List[StudentProgressResponse]

class BookResponse(BaseModel):
    book_id: int
    class_level: int
    subject: str
    author: str
    chapter: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)