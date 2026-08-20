from pathlib import Path
import pytest
from services.gamification import (
    TEACHER,
    TUTOR_PRACTICE,
    calculate_reward,
    normalize_assignment_source,
    repetition_multiplier,
    apply_daily_practice_cap,
    remaining_practice_coin_budget,
    infer_difficulty,
    is_substantive_learning_message,
)


def test_assignment_source_is_explicit_with_legacy_fallback_only():
    assert normalize_assignment_source("teacher", None) == TEACHER
    assert normalize_assignment_source("tutor_practice", 123) == TUTOR_PRACTICE
    assert normalize_assignment_source(None, 123) == TEACHER
    assert normalize_assignment_source(None, None) == TUTOR_PRACTICE


def test_tutor_practice_rewards_diminish_on_repetition():
    first = calculate_reward(
        assignment_source=TUTOR_PRACTICE,
        is_correct=True,
        quality_score=0.9,
        prior_success_count=0,
        question_count=5,
    )
    second = calculate_reward(
        assignment_source=TUTOR_PRACTICE,
        is_correct=True,
        quality_score=0.9,
        prior_success_count=1,
        question_count=5,
    )
    later = calculate_reward(
        assignment_source=TUTOR_PRACTICE,
        is_correct=True,
        quality_score=0.9,
        prior_success_count=5,
        question_count=5,
    )

    assert first.xp > second.xp > later.xp
    assert first.repetition_multiplier == 1.0
    assert second.repetition_multiplier == 0.30
    assert later.repetition_multiplier == 0.10
    assert second.coins == 0
    assert later.coins == 0


def test_one_question_practice_cannot_farm_coins_or_streak():
    reward = calculate_reward(
        assignment_source=TUTOR_PRACTICE,
        is_correct=True,
        quality_score=1.0,
        prior_success_count=0,
        question_count=1,
    )
    assert reward.xp > 0
    assert reward.coins == 0
    assert reward.meaningful_activity is False


def test_teacher_perfect_first_attempt_has_stronger_reward_than_basic_practice():
    teacher = calculate_reward(
        assignment_source=TEACHER,
        is_correct=True,
        quality_score=1.0,
        attempt_number=1,
        question_count=3,
    )
    practice = calculate_reward(
        assignment_source=TUTOR_PRACTICE,
        is_correct=True,
        quality_score=1.0,
        attempt_number=1,
        prior_success_count=0,
        question_count=3,
    )
    assert teacher.xp > practice.xp
    assert teacher.coins > 0
    assert teacher.meaningful_activity is True


def test_wrong_or_incomplete_result_never_receives_reward():
    wrong = calculate_reward(
        assignment_source=TEACHER,
        is_correct=False,
        completed=True,
        question_count=10,
    )
    incomplete = calculate_reward(
        assignment_source=TUTOR_PRACTICE,
        is_correct=True,
        completed=False,
        question_count=10,
    )
    assert (wrong.xp, wrong.coins, wrong.meaningful_activity) == (0, 0, False)
    assert (incomplete.xp, incomplete.coins, incomplete.meaningful_activity) == (0, 0, False)


def test_repetition_multiplier_contract():
    assert repetition_multiplier(0) == 1.0
    assert repetition_multiplier(1) == 0.30
    assert repetition_multiplier(2) == 0.10
    assert repetition_multiplier(100) == 0.10


class _DuplicateEventConn:
    def __init__(self):
        self.execute_calls = []

    async def execute(self, *args):
        self.execute_calls.append(args)
        return "OK"

    async def fetchrow(self, query, *args):
        if "FROM gamification WHERE user_id" in query:
            return {
                "balance_coins": 77,
                "xp_total": 321,
                "streak_days": 4,
                "last_learning_date": None,
                "active_days_total": 9,
                "streak_saves": 1,
            }
        raise AssertionError(f"unexpected fetchrow on duplicate path: {query}")

    async def fetchval(self, query, *args):
        if "SELECT EXISTS" in query and "gamification_events" in query:
            return True
        raise AssertionError(f"unexpected fetchval on duplicate path: {query}")


@pytest.mark.asyncio
async def test_same_task_completion_is_idempotent():
    from services.gamification import award_learning_result

    result = await award_learning_result(
        _DuplicateEventConn(),
        user_id=1,
        task_id=55,
        assignment_source=TUTOR_PRACTICE,
        subject="Математика",
        topic="Дроби",
        is_correct=True,
        question_count=5,
    )
    assert result.duplicate_event is True
    assert result.xp == 0
    assert result.coins == 0
    assert result.balance_coins == 77
    assert result.xp_total == 321


def test_daily_practice_cap_blocks_mass_generated_full_rewards():
    total_xp = 0
    total_direct_coins = 0
    for completed_today in range(100):
        reward = calculate_reward(
            assignment_source=TUTOR_PRACTICE,
            is_correct=True,
            quality_score=1.0,
            prior_success_count=0,  # even with 100 cosmetically different topic names
            question_count=5,
        )
        reward = apply_daily_practice_cap(reward, completed_today)
        total_xp += reward.xp
        total_direct_coins += reward.coins
    assert total_xp < 800
    assert total_direct_coins <= 15


def test_practice_coin_budget_has_hard_daily_limit():
    assert remaining_practice_coin_budget(0) == 15
    assert remaining_practice_coin_budget(10) == 5
    assert remaining_practice_coin_budget(15) == 0
    assert remaining_practice_coin_budget(1000) == 0


def test_difficulty_signal_is_detected_from_user_request():
    assert infer_difficulty("Сделай сложный квест по дробям") == "hard"
    assert infer_difficulty("advanced geometry quest") == "hard"
    assert infer_difficulty("обычная практика по дробям") == "normal"


def test_tutor_chat_streak_requires_substantive_learning_messages():
    assert is_substantive_learning_message("Привет") is False
    assert is_substantive_learning_message("Hi!") is False
    assert is_substantive_learning_message("Объясни, пожалуйста, почему при сложении дробей нужен общий знаменатель?") is True


def test_full_tutor_study_session_is_daily_and_not_per_message():
    service = Path(__file__).resolve().parents[1] / "services/gamification.py"
    text = service.read_text(encoding="utf-8")
    assert 'event_key = f"tutor-study:{today.isoformat()}"' in text
    assert "len(substantive) < 4" in text
    assert "assistant_turns < 4" in text
    assert "< 180" in text


def test_no_mistakes_achievement_requires_no_correction_marker():
    text = (Path(__file__).resolve().parents[1] / "services/gamification.py").read_text(encoding="utf-8")
    assert "question_count >= 3 and not corrected_after_hint" in text
    assert "corrected_mistakes" in text
