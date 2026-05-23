"""
ki Sync — Git version control for Anki collections.

This module registers Anki hooks only when running inside Anki.
The engine/ and formats/ layers can be imported and tested independently.
"""


def init_addon():
    try:
        from .addon import init_addon as _init
        _init()
    except ImportError:
        pass


init_addon()
