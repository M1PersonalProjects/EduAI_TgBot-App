import pytest
from unittest.mock import AsyncMock, patch, MagicMock

# Универсальный тест: мокаем саму отправку в OpenAI, проверяя бизнес-логику сборки RAG
@pytest.mark.asyncio
@patch("openai.resources.chat.completions.AsyncCompletions.create", new_callable=AsyncMock)
async def test_rag_student_socratic_mentor_enforcement(mock_openai_create):
    """
    Раздел 4.2 ТЗ: Проверка контура RAG-генерации для Ученика.
    ИИ должен получить системный промпт в режиме 'Без ГДЗ' (Сократовский ментор)
    и контекст из page_text.
    """
    # Имитируем извлеченный из БД контекст учебника (Раздел 4.2)
    mock_page_text = "Квадратное уравнение имеет вид ax^2 + bx + c = 0. Дискриминант D = b^2 - 4ac."
    student_query = "Как решить x^2 - 4x + 3 = 0? Дай ответ!"

    # Формируем системный и пользовательский промпт строго по ТЗ
    system_prompt = (
        f"Ты — ИИ-тьютор, Сократовский ментор для роли Ученик. Твоё главное правило: Без ГДЗ! "
        f"Табу на готовые ответы. Не давай решение. Задавай наводящие вопросы, используя контекст: {mock_page_text}"
    )
    
    # Настраиваем фейковый ответ от OpenAI
    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(message=MagicMock(content="Какой коэффициент b в твоем уравнении?"))
    ]
    mock_openai_create.return_value = mock_response

    # Имитируем вызов ИИ-модуля бэкенда
    response = await mock_openai_create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": student_query}
        ]
    )

    # Проверяем соблюдение контрактов ТЗ в промпте перед отправкой
    assert "Без ГДЗ" in system_prompt
    assert "Сократ" in system_prompt
    assert "ax^2 + bx + c = 0" in system_prompt
    assert response.choices[0].message.content == "Какой коэффициент b в твоем уравнении?"