from pydantic import BaseModel
from typing import Optional

class TaskGenerationResponse(BaseModel):
    task_id: int
    title: str
    description: str
    reward_coins: int
    reward_xp: int

class SubmitAnswerRequest(BaseModel):
    tg_id: int
    student_answer: str
    task_id: Optional[int] = None
    class_level: Optional[int] = None
    subject: Optional[str] = None
    book_id: Optional[int] = None
    topic_context: Optional[str] = None

class SubmitAnswerResponse(BaseModel):
    success: bool
    message: str
    new_balance_coins: int
    new_xp_total: int