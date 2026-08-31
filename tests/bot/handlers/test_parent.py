from pathlib import Path


def test_legacy_parent_handler_is_removed_and_not_registered():
    assert not Path("bot/handlers/parent.py").exists()
    main = Path("main.py").read_text(encoding="utf-8")
    assert "bot.handlers import parent" not in main
    assert "parent.router" not in main
