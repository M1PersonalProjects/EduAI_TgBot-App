from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Optional

from services.task_generation import extract_requested_task_count


_GRADE_RE = re.compile(
    r"(?:^|\b)(?:класс\s*)?(\d{1,2})(?:\s*[-–]?(?:й|ый|ой|го|ого))?\s*(?:класс(?:а|е)?|кл\.?|grade)\b",
    re.IGNORECASE,
)
_SUBJECT_LABEL_RE = re.compile(
    r"(?:предмет|subject)\s*[:=\-–]\s*([^;\n,]+)",
    re.IGNORECASE,
)
_TOPIC_LABEL_RE = re.compile(
    r"(?:тема|тему|topic)\s*[:=\-–]\s*([^;\n]+)",
    re.IGNORECASE,
)
_SUBJECT_TOPIC_RE = re.compile(
    r"\bпо\s+([^,;.\n]{2,80}?)\s+(?:на\s+)?тем(?:е|у|а)\s+([^,;.\n]{2,180})",
    re.IGNORECASE,
)
_COUNT_ONLY_RE = re.compile(
    r"^\s*\d{1,3}\s+(?:вопрос(?:а|ов|ы)?|задач(?:а|и|у|е|)?|задани(?:е|я|й|ю)|"
    r"упражнени(?:е|я|й|ю)|questions?|tasks?|problems?)\s*$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class QuestRequestSpec:
    grade: Optional[int]
    subject: str
    topic: str
    requested_count: int
    raw_request: str

    @property
    def missing_fields(self) -> tuple[str, ...]:
        missing: list[str] = []
        if self.grade is None:
            missing.append("класс")
        if not self.subject:
            missing.append("предмет")
        if not self.topic:
            missing.append("тема")
        return tuple(missing)


def _clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip(" \t\r\n,;.-–"))


def _segments(text: str) -> list[str]:
    return [
        _clean(part)
        for part in re.split(r"[;,\n]+", text or "")
        if _clean(part)
    ]


def parse_quest_request(
    text: str,
    *,
    grade: Optional[int] = None,
    subject: str = "",
    topic: str = "",
    default_count: int = 5,
) -> QuestRequestSpec:
    """Parse a Telegram quest request without requiring an extra LLM call.

    Existing catalog selections have priority. Free-form requests support both labelled
    input ("класс: 7; предмет: математика; тема: дроби") and the compact form
    "7 класс, математика, дроби, 5 вопросов".
    """
    raw = _clean(text)
    selected_grade = int(grade) if grade not in (None, "") else None
    selected_subject = _clean(subject)
    selected_topic = _clean(topic)

    if selected_grade is None:
        match = _GRADE_RE.search(raw)
        if match:
            value = int(match.group(1))
            if 1 <= value <= 11:
                selected_grade = value

    if not selected_subject:
        match = _SUBJECT_LABEL_RE.search(raw)
        if match:
            selected_subject = _clean(match.group(1))

    if not selected_topic:
        match = _TOPIC_LABEL_RE.search(raw)
        if match:
            selected_topic = _clean(match.group(1))

    phrase_match = _SUBJECT_TOPIC_RE.search(raw)
    if phrase_match:
        if not selected_subject:
            selected_subject = _clean(phrase_match.group(1))
        if not selected_topic:
            selected_topic = _clean(phrase_match.group(2))

    parts = _segments(raw)
    useful_parts: list[str] = []
    for part in parts:
        if _COUNT_ONLY_RE.match(part):
            continue
        if _GRADE_RE.search(part) and _clean(_GRADE_RE.sub("", part)) == "":
            continue
        if re.match(r"^(?:класс|предмет|тема|topic|subject)\s*[:=\-–]", part, re.I):
            continue
        useful_parts.append(part)

    if not selected_subject and useful_parts:
        selected_subject = useful_parts[0]
    if not selected_topic and len(useful_parts) >= 2:
        selected_topic = useful_parts[1]

    requested_count = extract_requested_task_count(raw, default=default_count, maximum=20)
    return QuestRequestSpec(
        grade=selected_grade,
        subject=selected_subject,
        topic=selected_topic,
        requested_count=requested_count,
        raw_request=raw,
    )


def canonicalize_subject(subject: str, candidates: list[str], *, threshold: float = 0.72) -> str:
    """Map a free-form/inflected subject name to an existing EduAI program when close enough."""
    value = _clean(subject)
    if not value or not candidates:
        return value
    folded = value.casefold().replace("ё", "е")
    exact = next(
        (item for item in candidates if _clean(item).casefold().replace("ё", "е") == folded),
        None,
    )
    if exact:
        return _clean(exact)
    scored = [
        (
            SequenceMatcher(
                None,
                folded,
                _clean(item).casefold().replace("ё", "е"),
            ).ratio(),
            _clean(item),
        )
        for item in candidates
        if _clean(item)
    ]
    if not scored:
        return value
    score, candidate = max(scored, key=lambda item: item[0])
    return candidate if score >= threshold else value
