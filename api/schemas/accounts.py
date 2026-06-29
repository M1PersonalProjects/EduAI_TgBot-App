from pydantic import BaseModel
from typing import List, Optional

class LinkAccountsRequest(BaseModel):
    parent_tg_id: int
    student_tg_id: int

class StudentProgressResponse(BaseModel):
    tg_id: int
    username: Optional[str] = None
    balance_coins: int
    xp_total: int
    streak_days: int

class MonitoringResponse(BaseModel):
    parent_tg_id: int
    students: List[StudentProgressResponse]

class BookResponse(BaseModel):
    book_id: int
    class_level: int
    subject: str
    author: str
    chapter: Optional[str] = None