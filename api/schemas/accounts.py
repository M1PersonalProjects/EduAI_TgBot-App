from pydantic import BaseModel, ConfigDict
from typing import List, Optional

class LinkAccountsRequest(BaseModel):
    parent_tg_id: int
    student_tg_id: int

class StudentProgressResponse(BaseModel):
    tg_id: int
    username: Optional[str] = None
    role: str

class MonitoringResponse(BaseModel):
    parent_tg_id: int
    students: List[StudentProgressResponse]

class WebAppAuthRequest(BaseModel):
    init_data_raw: str

class RoleSwitchRequest(BaseModel):
    tg_id: int
    target_role: str
    init_data_raw: str

class AuthResponse(BaseModel):
    status: str
    tg_id: int
    username: Optional[str]
    role: str

class BookResponse(BaseModel):
    book_id: int
    class_level: int
    subject: str
    author: str
    chapter: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

class WebAuthRequest(BaseModel):
    tg_id: int