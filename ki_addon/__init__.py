"""
ki Sync — Git version control for Anki collections.

This module registers Anki hooks only. All Qt UI and core logic
lives in addon.py and engine/ respectively.
"""

from .addon import init_addon

init_addon()
