"""Tests for UI utility functions."""
from unittest.mock import MagicMock


def test_run_on_main_sync_runs_fn_and_returns_value():
    from anki_git.ui.utils import run_on_main_sync

    mw = MagicMock()
    mw.taskman.run_on_main.side_effect = lambda fn: fn()

    result = run_on_main_sync(mw, lambda: 42)
    assert result == 42
    mw.taskman.run_on_main.assert_called_once()


def test_run_on_main_sync_raises_on_error():
    from anki_git.ui.utils import run_on_main_sync

    mw = MagicMock()

    def throw_error():
        raise ValueError("test error")

    mw.taskman.run_on_main.side_effect = lambda fn: fn()

    import pytest
    with pytest.raises(ValueError, match="test error"):
        run_on_main_sync(mw, throw_error)


def test_run_on_main_sync_runs_fn_with_args():
    from anki_git.ui.utils import run_on_main_sync

    mw = MagicMock()
    mw.taskman.run_on_main.side_effect = lambda fn: fn()

    captured = []

    def set_val():
        captured.append(99)
        return "ok"

    result = run_on_main_sync(mw, set_val)
    assert result == "ok"
    assert captured == [99]
