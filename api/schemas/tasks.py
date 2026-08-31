from pydantic import BaseModel, Field


class OpenAITaskVerification(BaseModel):
    """Структурированный результат AI-подсказки для проверки Учителем."""

    is_correct: bool = Field(..., description="True если ответ выглядит верным, иначе False")
    explanation: str = Field(..., description="Краткое объяснение для Учителя на русском языке")
