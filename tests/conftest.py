"""Test fixtures for AnkiGit addon tests.

Follows the pattern from Anki-Dictionary-Addon:
- anki_session: headless anki.collection.Collection backed by a temp DB
- mock_aqt_mw: stubbed aqt.mw for tests that need Qt symbols
"""
import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

try:
    from anki.collection import Collection as _AnkiCollection

    _anki_available = True
except ImportError:
    _anki_available = False


@pytest.fixture(scope="function")
def anki_session():
    """Create a headless real Anki collection for integration testing.

    Yields a namespace with:
      .collection -- anki.collection.Collection backed by a temp DB
      .base       -- temporary Anki base directory path
    """
    if not _anki_available:
        pytest.skip("anki package not available")

    base_dir = tempfile.mkdtemp(prefix="anki_git_int_")
    col_path = os.path.join(base_dir, "collection.anki2")
    col = _AnkiCollection(col_path)

    class Session:
        collection = col
        base = base_dir

        def cleanup(self):
            from contextlib import suppress
            with suppress(Exception):
                self.collection.close()
            with suppress(Exception):
                shutil.rmtree(self.base, ignore_errors=True)

    session = Session()
    try:
        yield session
    finally:
        session.cleanup()


@pytest.fixture
def mock_aqt_mw():
    """Provide a clean MagicMock for aqt.mw."""
    import aqt

    aqt.mw = MagicMock()
    aqt.mw.pm.addonFolder.return_value = str(
        Path.home() / ".local/share/Anki2/addons21"
    )
    return aqt.mw
