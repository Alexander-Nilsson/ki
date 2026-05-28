"""
AnkiGit — Git version control for Anki collections.

This module registers Anki hooks only when running inside Anki.
The engine/ and formats/ layers can be imported and tested independently.
"""

version = "0.1.4"


def init_addon():
    try:
        from .addon import init_addon as _init
        _init()
    except ImportError as e:
        if "aqt" not in str(e):
            import traceback
            traceback.print_exc()


init_addon()
