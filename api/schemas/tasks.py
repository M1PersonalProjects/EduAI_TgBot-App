from pydantic import BaseModel, Field, ConfigDict

class TaskGenerationResponse(BaseModel):
    task_id: int = Field(..., description="ID созданной задачи из tasks_history")
    title: str = Field(..., description="Заголовок квеста на русском языке")
    description: str = Field(..., description="Текст математической задачи без знаков $")

    model_config = ConfigDict(from_attributes=True)

class SubmitAnswerRequest(BaseModel):
    tg_id: int = Field(..., description="Telegram ID ученика")
    task_id: int = Field(..., description="ID проверяемой задачи")
    student_answer: str = Field(..., min_length=1, description="Ответ ученика")


class SubmitAnswerResponse(BaseModel):
    success: bool = Field(..., description="True, если ИИ признал ответ верным")
    message: str = Field(..., description="Дружелюбный фидбек от ИИ на русском языке")
    status: str = Field(default="completed", description="Текущий статус проверки")

    model_config = ConfigDict(from_attributes=True)

class OpenAITaskVerification(BaseModel):
    """Структурированный результат проверки ответа ученика."""

    is_correct: bool = Field(..., description="True если ответ верен, иначе False")
    explanation: str = Field(..., description="Доброжелательное объяснение для Ученика на русском языке")
