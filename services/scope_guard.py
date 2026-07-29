import re
from dataclasses import dataclass
from typing import Iterable, Optional, Sequence

from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from config import settings
from services.context_resolver import ResolvedContext


openai_client = AsyncOpenAI(
    api_key=settings.openai_api_key.get_secret_value()
)


class ScopeClassification(BaseModel):
    is_educational: bool = Field(
        ...,
        description="Относится ли запрос к обучению, объяснению материала или решению учебной задачи",
    )
    matches_selected_context: bool = Field(
        ...,
        description="Соответствует ли запрос выбранному предмету, учебнику и теме",
    )
    reason: str = Field(
        ...,
        description="Краткое объяснение решения классификатора",
    )


@dataclass
class ScopeGuardResult:
    allowed: bool
    reason: str
    refusal_message: Optional[str] = None


# Очевидные запросы, которые образовательный тьютор не должен обслуживать.
# Это первый дешёвый серверный слой, работающий до обращения к модели.
OUT_OF_SCOPE_PATTERNS: Sequence[re.Pattern[str]] = (
    re.compile(
        r"\b(рецепт|борщ|суп|пицц[аы]|приготовить|готовить|ингредиент)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(футбол|волейбол|баскетбол|хоккей|теннис|чемпионат|спортсмен)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(погода|курс валют|биткоин|акци[ия]|новости|президент)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(анекдот|шутк[ауи]|мем|фильм|сериал|песн[яию]|стих про любовь)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(программировани[ея]|python|javascript|java|react|docker|sql)\b",
        re.IGNORECASE,
    ),
)


# Формулировки, которые сами по себе являются образовательными.
EDUCATIONAL_PATTERNS: Sequence[re.Pattern[str]] = (
    re.compile(
        r"\b(объясни|помоги понять|решить|решение|задач[ауи]|пример|упражнение)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(правило|определение|теорема|формула|тема|параграф|учебник)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(проверь|ошибка|домашн\w*\s+работ|контрольн\w*\s+работ)\b",
        re.IGNORECASE,
    ),
)


def _normalize(value: str) -> str:
    value = (value or "").lower().replace("ё", "е")
    value = re.sub(r"[^a-zа-я0-9\s-]", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _tokenize(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-zа-я0-9]+", _normalize(value))
        if len(token) >= 3
    }


def _contains_pattern(
    value: str,
    patterns: Iterable[re.Pattern[str]],
) -> bool:
    return any(pattern.search(value or "") for pattern in patterns)


def build_refusal_message(
    context: Optional[ResolvedContext],
    reason: Optional[str] = None,
) -> str:
    if context:
        selected = f"Сейчас выбран учебник «{context.book_title}»"
        if context.book_class:
            selected += f", {context.book_class} класс"
        if context.page_number:
            selected += f", страница {context.page_number}"

        message = (
            f"{selected}. Ваш вопрос не относится к материалу выбранного "
            "учебника или текущей учебной теме. Пожалуйста, задайте вопрос "
            "по изучаемому материалу либо выберите другой предмет и учебник."
        )
    else:
        message = (
            "EduAI является образовательным помощником и отвечает только "
            "на вопросы, связанные с обучением, объяснением учебного материала "
            "и решением учебных задач. Пожалуйста, задайте учебный вопрос."
        )

    if reason:
        return f"{message}\n\nПричина: {reason}"

    return message


def _quick_check(
    message_text: str,
    context: Optional[ResolvedContext],
    attachment_text: str = "",
) -> Optional[ScopeGuardResult]:
    combined = f"{message_text}\n{attachment_text}".strip()

    if not combined:
        return ScopeGuardResult(
            allowed=False,
            reason="Пустой запрос",
            refusal_message=build_refusal_message(context),
        )

    if _contains_pattern(combined, OUT_OF_SCOPE_PATTERNS):
        return ScopeGuardResult(
            allowed=False,
            reason="Запрос относится к явно неучебной или посторонней области",
            refusal_message=build_refusal_message(context),
        )

    # При выбранном учебнике недостаточно проверить, что запрос просто учебный:
    # он ещё должен относиться именно к выбранному контексту.
    if context:
        request_tokens = _tokenize(combined)
        context_tokens = _tokenize(
            " ".join(
                [
                    context.book_title or "",
                    context.book_author or "",
                    context.book_program or "",
                    context.page_title or "",
                    context.page_paragraph or "",
                    context.content[:8000] or "",
                ]
            )
        )

        overlap = request_tokens.intersection(context_tokens)

        # Явное совпадение позволяет не обращаться к дополнительному
        # классификатору для большинства обычных вопросов.
        if len(overlap) >= 2:
            return ScopeGuardResult(
                allowed=True,
                reason="Запрос совпадает с материалом выбранного учебника",
            )

    return None


async def validate_request_scope(
    message_text: str,
    context: Optional[ResolvedContext],
    attachment_text: str = "",
) -> ScopeGuardResult:
    quick_result = _quick_check(
        message_text=message_text,
        context=context,
        attachment_text=attachment_text,
    )
    if quick_result is not None:
        return quick_result

    context_description = "Учебник не выбран."

    if context:
        context_description = (
            f"Название: {context.book_title}\n"
            f"Автор: {context.book_author}\n"
            f"Предмет/программа: {context.book_program}\n"
            f"Класс: {context.book_class}\n"
            f"Тема страницы: {context.page_title or 'не указана'}\n"
            f"Параграф: {context.page_paragraph or 'не указан'}\n"
            f"Материал:\n{context.content[:10000]}"
        )

    response = await openai_client.beta.chat.completions.parse(
        model="gpt-4o-mini",
        temperature=0,
        max_tokens=300,
        messages=[
            {
                "role": "system",
                "content": (
                    "Ты являешься серверным классификатором образовательной "
                    "платформы EduAI. Не отвечай на вопрос пользователя. "
                    "Определи только допустимость запроса.\n\n"
                    "Запрос допустим, только если одновременно выполнены условия:\n"
                    "1. Он связан с обучением, объяснением учебного материала, "
                    "проверкой работы или решением учебной задачи.\n"
                    "2. Если выбран учебник, запрос относится именно к предмету, "
                    "классу, теме или материалу этого учебника.\n"
                    "3. Запрос не требует перехода к другому предмету.\n"
                    "4. Совпадение только отдельных общих слов недостаточно.\n\n"
                    "Если учебник не выбран, разрешены образовательные вопросы "
                    "по школьным дисциплинам, но запрещены бытовые, развлекательные, "
                    "новостные, спортивные и иные неучебные запросы."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Выбранный контекст:\n{context_description}\n\n"
                    f"Запрос пользователя:\n{message_text}\n\n"
                    f"Текст вложения:\n{attachment_text[:6000]}"
                ),
            },
        ],
        response_format=ScopeClassification,
    )

    classification = response.choices[0].message.parsed

    allowed = bool(
        classification
        and classification.is_educational
        and classification.matches_selected_context
    )

    if allowed:
        return ScopeGuardResult(
            allowed=True,
            reason=classification.reason,
        )

    reason = (
        classification.reason
        if classification
        else "Запрос не прошёл проверку образовательной области"
    )

    return ScopeGuardResult(
        allowed=False,
        reason=reason,
        refusal_message=build_refusal_message(context),
    )