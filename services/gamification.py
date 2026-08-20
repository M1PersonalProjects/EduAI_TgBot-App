from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from datetime import date, timedelta
from typing import Any, Iterable

TEACHER = "teacher"
TUTOR_PRACTICE = "tutor_practice"
VALID_ASSIGNMENT_SOURCES = {TEACHER, TUTOR_PRACTICE}
PRACTICE_DAILY_FULL_XP_SESSIONS = 3
PRACTICE_DAILY_DIRECT_COIN_CAP = 15
PRACTICE_DAILY_MIN_XP = 6


@dataclass(frozen=True)
class RewardDecision:
    xp: int = 0
    coins: int = 0
    repetition_multiplier: float = 1.0
    meaningful_activity: bool = False
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class RewardResult:
    xp: int
    coins: int
    balance_coins: int
    xp_total: int
    streak_days: int
    streak_saves: int
    repetition_multiplier: float
    achievements: tuple[str, ...] = ()
    completed_goals: tuple[str, ...] = ()
    duplicate_event: bool = False


ACHIEVEMENTS = {
    "top_5": ("Топ 5", "Пять полезных учебных завершений."),
    "streak_7": ("7 дней подряд", "Семь активных учебных дней подряд."),
    "no_mistakes": ("Без ошибок", "Завершить сессию минимум из 3 вопросов без ошибок."),
    "mistakes_corrected_10": ("Исправил 10 ошибок", "Исправить десять ошибок после повторной попытки или подсказки."),
    "mastered_5_topics": ("Освоено 5 тем", "Впервые уверенно освоить пять разных тем."),
    "correct_100": ("100 правильных ответов", "Набрать сто правильных ответов в полезных учебных сессиях."),
    "challenging_quest": ("Сложный квест", "Успешно пройти сложный тренировочный квест."),
}


def normalize_assignment_source(value: str | None, parent_id: int | None = None) -> str:
    normalized = (value or "").strip().lower()
    if normalized in VALID_ASSIGNMENT_SOURCES:
        return normalized
    # Compatibility only for pre-migration rows. New code must always write source.
    return TEACHER if parent_id is not None else TUTOR_PRACTICE


def make_topic_key(subject: str | None, topic: str | None) -> str:
    text = f"{subject or ''}::{topic or ''}".lower().replace("ё", "е")
    text = re.sub(r"[^a-zа-я0-9]+", "-", text, flags=re.IGNORECASE).strip("-")
    return text[:180] or "general-practice"


def infer_difficulty(*values: Any) -> str:
    text = " ".join(str(value or "") for value in values).lower().replace("ё", "е")
    if re.search(r"\b(hard|challenging|difficult|advanced|сложн\w*|повышенн\w*|олимпиадн\w*)\b", text):
        return "hard"
    return "normal"


def repetition_multiplier(prior_success_count: int) -> float:
    if prior_success_count <= 0:
        return 1.0
    if prior_success_count == 1:
        return 0.30
    return 0.10


def calculate_reward(
    *,
    assignment_source: str,
    is_correct: bool,
    completed: bool = True,
    quality_score: float = 1.0,
    attempt_number: int = 1,
    prior_success_count: int = 0,
    improvement: float = 0.0,
    difficulty: str = "normal",
    question_count: int = 1,
    corrected_after_hint: bool = False,
) -> RewardDecision:
    """Pure anti-farm reward policy shared by WebApp and Telegram."""
    source = normalize_assignment_source(assignment_source)
    quality = min(1.0, max(0.0, float(quality_score or 0)))
    questions = max(1, int(question_count or 1))
    if not is_correct or not completed:
        return RewardDecision()

    difficult = str(difficulty or "normal").strip().lower() in {
        "hard", "challenging", "difficult", "сложно", "сложный", "повышенная", "повышенной",
    }
    reasons: list[str] = []

    if source == TEACHER:
        xp = 45
        reasons.append("teacher_assignment")
        if quality >= 0.80:
            xp += 10
        if quality >= 0.95:
            xp += 10
        if attempt_number <= 1:
            xp += 10
        if improvement >= 0.10:
            xp += min(20, max(5, round(improvement * 100)))
            reasons.append("improvement")
        if difficult:
            xp += 15
            reasons.append("challenge")
        if corrected_after_hint:
            xp += 8
            reasons.append("corrected_mistake")

        coins = 0
        if quality >= 0.95 and attempt_number <= 1:
            coins += 15
            reasons.append("perfect_teacher_work")
        if improvement >= 0.15:
            coins += 8
        if difficult and quality >= 0.80:
            coins += 6
        return RewardDecision(
            xp=max(1, xp),
            coins=coins,
            meaningful_activity=True,
            reasons=tuple(reasons),
        )

    multiplier = repetition_multiplier(prior_success_count)
    base_xp = 30 if questions >= 3 else 10
    if quality >= 0.90:
        base_xp += 12 if questions >= 3 else 4
    if improvement >= 0.10:
        base_xp += 12
        reasons.append("improvement")
    if difficult:
        base_xp += 12
        reasons.append("challenge")
    if corrected_after_hint:
        base_xp += 6
        reasons.append("corrected_mistake")

    xp = max(4, round(base_xp * multiplier))
    coins = 0
    # Coins for practice are deliberately scarce and are never granted for
    # repeatedly generating the same easy one-question test.
    if prior_success_count == 0:
        if difficult and quality >= 0.80 and questions >= 3:
            coins += 8
        elif quality >= 0.95 and questions >= 5:
            coins += 5
    if improvement >= 0.15:
        coins += 6

    reasons.append("first_practice" if prior_success_count == 0 else "repeated_practice")
    return RewardDecision(
        xp=xp,
        coins=coins,
        repetition_multiplier=multiplier,
        meaningful_activity=questions >= 3 and quality >= 0.60,
        reasons=tuple(reasons),
    )


def apply_daily_practice_cap(decision: RewardDecision, daily_meaningful_sessions: int) -> RewardDecision:
    """Reduce self-created practice to maintenance XP after the daily useful quota."""
    if daily_meaningful_sessions < PRACTICE_DAILY_FULL_XP_SESSIONS:
        return decision
    return replace(
        decision,
        xp=min(decision.xp, PRACTICE_DAILY_MIN_XP),
        coins=0,
        repetition_multiplier=min(decision.repetition_multiplier, 0.10),
        reasons=tuple((*decision.reasons, "daily_practice_cap")),
    )


def remaining_practice_coin_budget(today_earned: int) -> int:
    return max(0, PRACTICE_DAILY_DIRECT_COIN_CAP - max(0, int(today_earned or 0)))


def is_substantive_learning_message(value: str | None) -> bool:
    """Reject greetings/noise when deciding whether chat was a real study session."""
    text = re.sub(r"\s+", " ", str(value or "")).strip().lower().replace("ё", "е")
    if not text:
        return False
    if re.fullmatch(r"(?:привет|здравствуй(?:те)?|добрый (?:день|вечер|утро)|hi|hello|hey)[!. ,]*", text):
        return False
    words = re.findall(r"[a-zа-я0-9]+", text, flags=re.IGNORECASE)
    return len(text) >= 18 and len(words) >= 4


def _next_streak_state(stats: Any, today: date) -> tuple[int, int, int, date | None]:
    streak_days = int(_row_value(stats, "streak_days", 0))
    streak_saves = int(_row_value(stats, "streak_saves", 0))
    active_days = int(_row_value(stats, "active_days_total", 0))
    last_learning_date = _row_value(stats, "last_learning_date")
    if isinstance(last_learning_date, str):
        try:
            last_learning_date = date.fromisoformat(last_learning_date)
        except ValueError:
            last_learning_date = None

    if last_learning_date != today:
        if last_learning_date == today - timedelta(days=1):
            streak_days += 1
        elif last_learning_date == today - timedelta(days=2) and streak_saves > 0:
            streak_days += 1
            streak_saves -= 1
        else:
            streak_days = 1
        active_days += 1
        if active_days % 7 == 0 and streak_saves < 2:
            streak_saves += 1
        last_learning_date = today
    return streak_days, streak_saves, active_days, last_learning_date


def _row_value(row: Any, key: str, default: Any = None) -> Any:
    if row is None:
        return default
    try:
        value = row[key]
    except (KeyError, TypeError):
        value = getattr(row, key, default)
    return default if value is None else value


async def _ensure_gamification_row(conn, user_id: int) -> Any:
    await conn.execute(
        """
        INSERT INTO gamification (user_id, balance_coins, xp_total, streak_days)
        VALUES ($1, 0, 0, 0)
        ON CONFLICT (user_id) DO NOTHING
        """,
        user_id,
    )
    return await conn.fetchrow(
        """
        SELECT balance_coins, xp_total, streak_days, last_learning_date,
               active_days_total, streak_saves
        FROM gamification WHERE user_id = $1
        FOR UPDATE
        """,
        user_id,
    )


async def _ensure_goals(conn, user_id: int, today: date) -> None:
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    recent_correct = await conn.fetchval(
        """
        SELECT COALESCE(SUM((metadata->>'correct_answers')::int), 0)
        FROM gamification_events
        WHERE user_id=$1 AND created_at >= CURRENT_TIMESTAMP - INTERVAL '7 days'
          AND COALESCE(metadata->>'success','false')='true'
        """,
        user_id,
    ) or 0
    daily_target = min(8, max(3, round(int(recent_correct) / 7) + 1))
    recent_sessions = await conn.fetchval(
        """
        SELECT COUNT(*) FROM gamification_events
        WHERE user_id=$1 AND created_at >= CURRENT_TIMESTAMP - INTERVAL '7 days'
          AND COALESCE(metadata->>'meaningful','false')='true'
          AND COALESCE(metadata->>'success','false')='true'
        """,
        user_id,
    ) or 0
    weekly_target = min(5, max(2, round(int(recent_sessions) / 2) + 1))

    await conn.execute(
        """
        INSERT INTO learning_goals (
            user_id, period_type, goal_code, title, target_value, progress_value,
            reward_xp, reward_coins, starts_on, ends_on
        ) VALUES ($1,'daily','correct_answers',$2,$3,0,15,0,$4,$4)
        ON CONFLICT (user_id, period_type, goal_code, starts_on) DO NOTHING
        """,
        user_id,
        f"Сегодня: правильно решить {daily_target} заданий",
        daily_target,
        today,
    )
    await conn.execute(
        """
        INSERT INTO learning_goals (
            user_id, period_type, goal_code, title, target_value, progress_value,
            reward_xp, reward_coins, starts_on, ends_on
        ) VALUES ($1,'weekly','study_sessions',$2,$3,0,0,20,$4,$5)
        ON CONFLICT (user_id, period_type, goal_code, starts_on) DO NOTHING
        """,
        user_id,
        f"На неделе: завершить {weekly_target} полезных учебных сессий",
        weekly_target,
        week_start,
        week_end,
    )


async def _advance_goals(
    conn,
    user_id: int,
    *,
    correct_answers: int,
    meaningful: bool,
    today: date,
) -> tuple[int, int, tuple[str, ...]]:
    await _ensure_goals(conn, user_id, today)
    week_start = today - timedelta(days=today.weekday())
    if correct_answers > 0:
        await conn.execute(
            """
            UPDATE learning_goals
            SET progress_value = LEAST(target_value, progress_value + $1),
                completed_at = CASE
                    WHEN progress_value + $1 >= target_value THEN COALESCE(completed_at, CURRENT_TIMESTAMP)
                    ELSE completed_at END
            WHERE user_id=$2 AND period_type='daily' AND goal_code='correct_answers'
              AND starts_on=$3
            """,
            correct_answers,
            user_id,
            today,
        )
    if meaningful:
        await conn.execute(
            """
            UPDATE learning_goals
            SET progress_value = LEAST(target_value, progress_value + 1),
                completed_at = CASE
                    WHEN progress_value + 1 >= target_value THEN COALESCE(completed_at, CURRENT_TIMESTAMP)
                    ELSE completed_at END
            WHERE user_id=$1 AND period_type='weekly' AND goal_code='study_sessions'
              AND starts_on=$2
            """,
            user_id,
            week_start,
        )
    rows = await conn.fetch(
        """
        UPDATE learning_goals
        SET rewarded_at=CURRENT_TIMESTAMP
        WHERE user_id=$1 AND completed_at IS NOT NULL AND rewarded_at IS NULL
          AND starts_on <= $2 AND ends_on >= $2
        RETURNING title, reward_xp, reward_coins
        """,
        user_id,
        today,
    )
    return (
        sum(int(_row_value(row, "reward_xp", 0)) for row in rows),
        sum(int(_row_value(row, "reward_coins", 0)) for row in rows),
        tuple(str(_row_value(row, "title", "Цель выполнена")) for row in rows),
    )


async def _unlock_achievements(
    conn,
    user_id: int,
    *,
    streak_days: int,
    quality_score: float,
    question_count: int,
    corrected_after_hint: bool,
    difficulty: str,
    assignment_source: str,
) -> tuple[str, ...]:
    successful_events = await conn.fetchval(
        """
        SELECT COUNT(*) FROM gamification_events
        WHERE user_id=$1 AND COALESCE(metadata->>'success','false')='true'
          AND COALESCE(metadata->>'meaningful','false')='true'
        """,
        user_id,
    ) or 0
    corrected = await conn.fetchval(
        """
        SELECT COALESCE(SUM(COALESCE((metadata->>'corrected_mistakes')::int, 0)), 0)
        FROM gamification_events
        WHERE user_id=$1
        """,
        user_id,
    ) or 0
    correct_answers = await conn.fetchval(
        """
        SELECT COALESCE(SUM((metadata->>'correct_answers')::int),0)
        FROM gamification_events
        WHERE user_id=$1 AND COALESCE(metadata->>'success','false')='true'
        """,
        user_id,
    ) or 0
    mastered = await conn.fetchval(
        "SELECT COUNT(*) FROM student_topic_mastery WHERE user_id=$1 AND first_mastered_at IS NOT NULL",
        user_id,
    ) or 0

    wanted: list[str] = []
    if successful_events >= 5:
        wanted.append("top_5")
    if streak_days >= 7:
        wanted.append("streak_7")
    if quality_score >= 0.999 and question_count >= 3 and not corrected_after_hint:
        wanted.append("no_mistakes")
    if corrected >= 10:
        wanted.append("mistakes_corrected_10")
    if mastered >= 5:
        wanted.append("mastered_5_topics")
    if correct_answers >= 100:
        wanted.append("correct_100")
    if assignment_source == TUTOR_PRACTICE and difficulty.lower() in {"hard", "challenging", "difficult", "сложно", "сложный"} and quality_score >= 0.80:
        wanted.append("challenging_quest")

    unlocked: list[str] = []
    for code in wanted:
        title, description = ACHIEVEMENTS[code]
        row = await conn.fetchrow(
            """
            INSERT INTO student_achievements (user_id, code, title, description)
            VALUES ($1,$2,$3,$4)
            ON CONFLICT (user_id, code) DO NOTHING
            RETURNING code
            """,
            user_id,
            code,
            title,
            description,
        )
        if row:
            unlocked.append(code)
    return tuple(unlocked)


async def award_learning_result(
    conn,
    *,
    user_id: int,
    task_id: int,
    assignment_source: str,
    subject: str = "",
    topic: str = "",
    is_correct: bool,
    completed: bool = True,
    quality_score: float = 1.0,
    attempt_number: int = 1,
    question_count: int = 1,
    difficulty: str = "normal",
    corrected_after_hint: bool = False,
    corrected_mistakes: int = 0,
) -> RewardResult:
    source = normalize_assignment_source(assignment_source)
    topic_key = make_topic_key(subject, topic)
    today = date.today()
    stats = await _ensure_gamification_row(conn, user_id)

    duplicate = await conn.fetchval(
        "SELECT EXISTS(SELECT 1 FROM gamification_events WHERE user_id=$1 AND event_key=$2)",
        user_id,
        f"task:{task_id}:complete",
    )
    if duplicate:
        return RewardResult(
            xp=0,
            coins=0,
            balance_coins=int(_row_value(stats, "balance_coins", 0)),
            xp_total=int(_row_value(stats, "xp_total", 0)),
            streak_days=int(_row_value(stats, "streak_days", 0)),
            streak_saves=int(_row_value(stats, "streak_saves", 0)),
            repetition_multiplier=0.0,
            duplicate_event=True,
        )

    prior_success_count = 0
    daily_practice_sessions = 0
    daily_practice_coins = 0
    if source == TUTOR_PRACTICE:
        prior_success_count = int(await conn.fetchval(
            """
            SELECT COUNT(*) FROM gamification_events
            WHERE user_id=$1 AND assignment_source='tutor_practice' AND topic_key=$2
              AND COALESCE(metadata->>'success','false')='true'
              AND created_at >= CURRENT_TIMESTAMP - INTERVAL '30 days'
            """,
            user_id,
            topic_key,
        ) or 0)
        daily_practice_sessions = int(await conn.fetchval(
            """
            SELECT COUNT(*) FROM gamification_events
            WHERE user_id=$1 AND assignment_source='tutor_practice'
              AND COALESCE(metadata->>'success','false')='true'
              AND COALESCE(metadata->>'meaningful','false')='true'
              AND created_at >= CURRENT_DATE
            """,
            user_id,
        ) or 0)
        daily_practice_coins = int(await conn.fetchval(
            """
            SELECT COALESCE(SUM(coins_delta),0) FROM gamification_events
            WHERE user_id=$1 AND assignment_source='tutor_practice'
              AND created_at >= CURRENT_DATE
            """,
            user_id,
        ) or 0)

    previous_best = float(await conn.fetchval(
        """
        SELECT COALESCE(MAX(quality_score),0) FROM gamification_events
        WHERE user_id=$1 AND topic_key=$2 AND COALESCE(metadata->>'success','false')='true'
        """,
        user_id,
        topic_key,
    ) or 0)
    quality = min(1.0, max(0.0, float(quality_score or 0)))
    improvement = max(0.0, quality - previous_best) if previous_best > 0 else 0.0

    decision = calculate_reward(
        assignment_source=source,
        is_correct=is_correct,
        completed=completed,
        quality_score=quality,
        attempt_number=attempt_number,
        prior_success_count=prior_success_count,
        improvement=improvement,
        difficulty=difficulty,
        question_count=question_count,
        corrected_after_hint=corrected_after_hint,
    )
    if source == TUTOR_PRACTICE:
        decision = apply_daily_practice_cap(decision, daily_practice_sessions)

    mastery_bonus_xp = 0
    mastery_bonus_coins = 0
    # A first-mastery bonus is intentionally tied to meaningful learning.
    # This prevents farming coins by generating endless one-question practice tasks.
    mastery_eligible = decision.meaningful_activity and is_correct and completed and quality >= 0.80
    if mastery_eligible and (source == TEACHER or daily_practice_sessions < PRACTICE_DAILY_FULL_XP_SESSIONS):
        mastery = await conn.fetchrow(
            "SELECT first_mastered_at, best_quality FROM student_topic_mastery WHERE user_id=$1 AND topic_key=$2 FOR UPDATE",
            user_id,
            topic_key,
        )
        first_mastery = not mastery or not _row_value(mastery, "first_mastered_at")
        await conn.execute(
            """
            INSERT INTO student_topic_mastery (
                user_id, topic_key, subject, topic, successful_sessions, best_quality, first_mastered_at
            ) VALUES ($1,$2,$3,$4,1,$5,CURRENT_TIMESTAMP)
            ON CONFLICT (user_id, topic_key) DO UPDATE
            SET successful_sessions=student_topic_mastery.successful_sessions+1,
                best_quality=GREATEST(student_topic_mastery.best_quality, EXCLUDED.best_quality),
                first_mastered_at=COALESCE(student_topic_mastery.first_mastered_at, CURRENT_TIMESTAMP),
                updated_at=CURRENT_TIMESTAMP
            """,
            user_id,
            topic_key,
            subject or "",
            topic or "",
            quality,
        )
        if first_mastery:
            mastery_bonus_xp = 15
            mastery_bonus_coins = 10

    if source == TUTOR_PRACTICE:
        # Direct AI-practice coins have a daily budget. Goal/achievement rewards
        # are applied later and intentionally stay outside this farming cap.
        budget = remaining_practice_coin_budget(daily_practice_coins)
        mastery_bonus_coins = min(mastery_bonus_coins, budget)
        budget -= mastery_bonus_coins
        decision = replace(decision, coins=min(decision.coins, budget))

    if decision.meaningful_activity:
        streak_days, streak_saves, active_days, last_learning_date = _next_streak_state(stats, today)
    else:
        streak_days = int(_row_value(stats, "streak_days", 0))
        streak_saves = int(_row_value(stats, "streak_saves", 0))
        active_days = int(_row_value(stats, "active_days_total", 0))
        last_learning_date = _row_value(stats, "last_learning_date")

    correct_answers = max(1, int(question_count or 1)) if is_correct and completed else 0
    corrected_count = max(int(corrected_mistakes or 0), 1 if corrected_after_hint else 0)
    metadata = {
        "success": bool(is_correct and completed),
        "meaningful": bool(decision.meaningful_activity),
        "correct_answers": correct_answers,
        "attempt_number": int(attempt_number),
        "question_count": max(1, int(question_count or 1)),
        "difficulty": difficulty,
        "corrected_after_hint": bool(corrected_after_hint),
        "corrected_mistakes": corrected_count,
        "improvement": improvement,
        "repetition_multiplier": decision.repetition_multiplier,
        "reasons": list(decision.reasons),
    }

    inserted = await conn.fetchrow(
        """
        INSERT INTO gamification_events (
            user_id, event_key, event_type, assignment_source, task_id, topic_key,
            xp_delta, coins_delta, quality_score, metadata
        ) VALUES ($1,$2,'task_completed',$3,$4,$5,$6,$7,$8,$9::jsonb)
        ON CONFLICT (user_id, event_key) DO NOTHING
        RETURNING event_id
        """,
        user_id,
        f"task:{task_id}:complete",
        source,
        task_id,
        topic_key,
        decision.xp + mastery_bonus_xp,
        decision.coins + mastery_bonus_coins,
        quality,
        json.dumps(metadata, ensure_ascii=False),
    )
    if not inserted:
        return RewardResult(
            xp=0,
            coins=0,
            balance_coins=int(_row_value(stats, "balance_coins", 0)),
            xp_total=int(_row_value(stats, "xp_total", 0)),
            streak_days=int(_row_value(stats, "streak_days", 0)),
            streak_saves=int(_row_value(stats, "streak_saves", 0)),
            repetition_multiplier=0.0,
            duplicate_event=True,
        )

    goal_xp, goal_coins, completed_goals = await _advance_goals(
        conn,
        user_id,
        correct_answers=correct_answers,
        meaningful=decision.meaningful_activity,
        today=today,
    )
    total_xp = decision.xp + mastery_bonus_xp + goal_xp
    total_coins = decision.coins + mastery_bonus_coins + goal_coins

    updated_stats = await conn.fetchrow(
        """
        UPDATE gamification
        SET balance_coins=balance_coins+$1,
            xp_total=xp_total+$2,
            streak_days=$3,
            last_learning_date=$4,
            active_days_total=$5,
            streak_saves=$6
        WHERE user_id=$7
        RETURNING balance_coins, xp_total, streak_days, streak_saves
        """,
        total_coins,
        total_xp,
        streak_days,
        last_learning_date,
        active_days,
        streak_saves,
        user_id,
    )

    achievements = await _unlock_achievements(
        conn,
        user_id,
        streak_days=streak_days,
        quality_score=quality,
        question_count=max(1, int(question_count or 1)),
        corrected_after_hint=corrected_after_hint,
        difficulty=difficulty,
        assignment_source=source,
    )
    achievement_coins = 5 * len(achievements)
    if achievement_coins:
        updated_stats = await conn.fetchrow(
            """
            UPDATE gamification
            SET balance_coins=balance_coins+$1
            WHERE user_id=$2
            RETURNING balance_coins, xp_total, streak_days, streak_saves
            """,
            achievement_coins,
            user_id,
        )
        total_coins += achievement_coins

    # Keep the immutable event ledger aligned with all bonuses caused by this event.
    if goal_xp or goal_coins or achievement_coins:
        await conn.execute(
            """
            UPDATE gamification_events
            SET xp_delta=xp_delta+$1, coins_delta=coins_delta+$2
            WHERE user_id=$3 AND event_key=$4
            """,
            goal_xp,
            goal_coins + achievement_coins,
            user_id,
            f"task:{task_id}:complete",
        )

    return RewardResult(
        xp=total_xp,
        coins=total_coins,
        balance_coins=int(_row_value(updated_stats, "balance_coins", 0)),
        xp_total=int(_row_value(updated_stats, "xp_total", 0)),
        streak_days=int(_row_value(updated_stats, "streak_days", streak_days)),
        streak_saves=int(_row_value(updated_stats, "streak_saves", streak_saves)),
        repetition_multiplier=decision.repetition_multiplier,
        achievements=tuple(ACHIEVEMENTS[code][0] for code in achievements),
        completed_goals=completed_goals,
    )


async def award_tutor_study_session_if_eligible(
    conn,
    *,
    user_id: int,
    session_id: Any,
) -> RewardResult | None:
    """Award one modest XP milestone per day for a genuinely substantive tutor chat.

    A greeting or a couple of short messages can never extend the streak. The learner
    must have at least four substantive turns, four tutor replies and enough total
    written context. The daily event key makes opening many new chats useless for farming.
    """
    rows = await conn.fetch(
        """
        SELECT sender, message_text
        FROM chat_messages
        WHERE user_id=$1 AND session_id=$2
        ORDER BY message_id ASC
        """,
        user_id,
        session_id,
    )
    user_messages = [
        str(_row_value(row, "message_text", ""))
        for row in rows
        if str(_row_value(row, "sender", "")) == "user"
    ]
    substantive = [text for text in user_messages if is_substantive_learning_message(text)]
    assistant_turns = sum(1 for row in rows if str(_row_value(row, "sender", "")) == "ai")
    if len(substantive) < 4 or assistant_turns < 4 or sum(len(text) for text in substantive) < 180:
        return None

    today = date.today()
    event_key = f"tutor-study:{today.isoformat()}"
    stats = await _ensure_gamification_row(conn, user_id)
    duplicate = await conn.fetchval(
        "SELECT EXISTS(SELECT 1 FROM gamification_events WHERE user_id=$1 AND event_key=$2)",
        user_id,
        event_key,
    )
    if duplicate:
        return None

    streak_days, streak_saves, active_days, last_learning_date = _next_streak_state(stats, today)
    base_xp = 18
    metadata = {
        "success": True,
        "meaningful": True,
        "correct_answers": 0,
        "study_session": True,
        "substantive_user_turns": len(substantive),
        "assistant_turns": assistant_turns,
        "session_id": str(session_id),
    }
    inserted = await conn.fetchrow(
        """
        INSERT INTO gamification_events (
            user_id, event_key, event_type, assignment_source, task_id, topic_key,
            xp_delta, coins_delta, quality_score, metadata
        ) VALUES ($1,$2,'tutor_study_session','tutor_practice',NULL,'tutor-chat',$3,0,0,$4::jsonb)
        ON CONFLICT (user_id, event_key) DO NOTHING
        RETURNING event_id
        """,
        user_id,
        event_key,
        base_xp,
        json.dumps(metadata, ensure_ascii=False),
    )
    if not inserted:
        return None

    goal_xp, goal_coins, completed_goals = await _advance_goals(
        conn, user_id, correct_answers=0, meaningful=True, today=today
    )
    total_xp = base_xp + goal_xp
    total_coins = goal_coins
    updated_stats = await conn.fetchrow(
        """
        UPDATE gamification
        SET balance_coins=balance_coins+$1, xp_total=xp_total+$2, streak_days=$3,
            last_learning_date=$4, active_days_total=$5, streak_saves=$6
        WHERE user_id=$7
        RETURNING balance_coins, xp_total, streak_days, streak_saves
        """,
        total_coins, total_xp, streak_days, last_learning_date, active_days, streak_saves, user_id,
    )
    achievements = await _unlock_achievements(
        conn,
        user_id,
        streak_days=streak_days,
        quality_score=0.0,
        question_count=0,
        corrected_after_hint=False,
        difficulty="normal",
        assignment_source=TUTOR_PRACTICE,
    )
    achievement_coins = 5 * len(achievements)
    if achievement_coins:
        updated_stats = await conn.fetchrow(
            """
            UPDATE gamification SET balance_coins=balance_coins+$1 WHERE user_id=$2
            RETURNING balance_coins, xp_total, streak_days, streak_saves
            """,
            achievement_coins,
            user_id,
        )
        total_coins += achievement_coins
    if goal_xp or goal_coins or achievement_coins:
        await conn.execute(
            """
            UPDATE gamification_events
            SET xp_delta=xp_delta+$1, coins_delta=coins_delta+$2
            WHERE user_id=$3 AND event_key=$4
            """,
            goal_xp, goal_coins + achievement_coins, user_id, event_key,
        )
    return RewardResult(
        xp=total_xp,
        coins=total_coins,
        balance_coins=int(_row_value(updated_stats, "balance_coins", 0)),
        xp_total=int(_row_value(updated_stats, "xp_total", 0)),
        streak_days=int(_row_value(updated_stats, "streak_days", streak_days)),
        streak_saves=int(_row_value(updated_stats, "streak_saves", streak_saves)),
        repetition_multiplier=1.0,
        achievements=tuple(ACHIEVEMENTS[code][0] for code in achievements),
        completed_goals=completed_goals,
    )


async def get_gamification_snapshot(conn, user_id: int) -> dict[str, Any]:
    today = date.today()
    await _ensure_goals(conn, user_id, today)
    achievements = await conn.fetch(
        """
        SELECT code, title, description, unlocked_at
        FROM student_achievements WHERE user_id=$1
        ORDER BY unlocked_at DESC LIMIT 20
        """,
        user_id,
    )
    goals = await conn.fetch(
        """
        SELECT period_type, goal_code, title, target_value, progress_value,
               reward_xp, reward_coins, starts_on, ends_on, completed_at
        FROM learning_goals
        WHERE user_id=$1 AND starts_on <= $2 AND ends_on >= $2
        ORDER BY period_type, goal_id
        """,
        user_id,
        today,
    )
    return {
        "achievements": [dict(row) for row in achievements],
        "goals": [dict(row) for row in goals],
    }
