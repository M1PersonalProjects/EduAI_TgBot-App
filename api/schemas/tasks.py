from pydantic import BaseModel, Field, ConfigDict
from typing import Optional

class TaskGenerationResponse(BaseModel):
    task_id: int = Field(..., description="ID созданной задачи из tasks_history")
    title: str = Field(..., description="Заголовок квеста на русском языке")
    description: str = Field(..., description="Текст математической задачи без знаков $")
    reward_coins: int = Field(..., description="Количество монет за успешное решение")
    reward_xp: int = Field(..., description="Количество опыта за успешное решение")

    model_config = ConfigDict(from_attributes=True)

class SubmitAnswerRequest(BaseModel):
    tg_id: int = Field(..., description="Telegram ID ученика")
    task_id: int = Field(..., description="ID проверяемой задачи")
    student_answer: str = Field(..., min_length=1, description="Ответ ученика")


class SubmitAnswerResponse(BaseModel):
    success: bool = Field(..., description="True, если ИИ признал ответ верным")
    message: str = Field(..., description="Дружелюбный фидбек от ИИ на русском языке")
    new_balance_coins: int = Field(..., description="Обновленный баланс монет ученика")
    new_xp_total: int = Field(..., description="Обновленный общий опыт ученика")

    model_config = ConfigDict(from_attributes=True)