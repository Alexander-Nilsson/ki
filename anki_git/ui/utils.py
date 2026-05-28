"""Shared UI utilities for AnkiGit dialogs."""

from collections.abc import Callable
from typing import Any


def run_on_main_sync(mw, fn: Callable[[], Any]) -> Any:
    """Execute fn on Anki's main thread and block until it returns.

    Safe to call from any thread. Uses threading.Event to synchronise.
    fn is called with no arguments and should return the result value.
    """
    import threading
    event = threading.Event()
    result: list[Any] = [None]
    errors: list[Any] = [None]

    def wrapper():
        try:
            result[0] = fn()
        except Exception as e:
            errors[0] = e
        finally:
            event.set()

    mw.taskman.run_on_main(wrapper)
    event.wait()
    if errors[0]:
        raise errors[0]  # type: ignore[misc]
    return result[0]
