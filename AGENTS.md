# AGENTS.md — AnkiGit

Anki addon providing Git-based version control for Anki collections. Export collections to a human-readable Git repo.

## Architecture

```
anki_git/
├── __init__.py          # Hook registration only; calls init_addon() on import
├── addon.py             # Qt UI: menus, dialogs, hook wiring
├── config.py            # KiSyncConfig dataclass (legacy naming from ki)
├── engine/              # NEVER import aqt here — must be testable without Anki
│   ├── exporter.py      # Anki→files (one-way snapshot)
│   ├── importer.py      # files→Anki (one-way pull; stale: looks for notes.md, not per-nid.md)
│   ├── sync.py          # Two-way sync: merge changes in both directions
│   ├── git_ops.py       # GitPython operations
│   ├── conflict.py      # Three-way merge + auto-resolution by sync_mode
│   └── checksums.py     # meta.json hashing
├── formats/
│   ├── notes_md.py      # One file per note: decks/<Deck>/<nid>.md
│   ├── notetype_yaml.py # notetypes/<Name>.yaml + <Name>.css
│   └── media.py
├── ui/
│   ├── settings.py      # Settings dialog (includes sync_mode selector)
│   ├── conflicts.py     # Conflict resolution dialog
│   └── progress.py      # Progress widgets
└── config.json          # Anki addon config manager schema
```

## Sync Modes (config.sync_mode)
- `always_ask` — show conflict dialog for true conflicts (default)
- `prefer_anki` — auto-resolve conflicts in favor of Anki side
- `prefer_repo` — auto-resolve conflicts in favor of repo side
- `accept_all` — auto-accept non-conflicting changes; for true conflicts Anki wins

## Critical Rules

- **engine/ must never import aqt** — only `anki`. Addon.py + ui/ handle Qt.
- **Collection writes only on main thread** via `mw.taskman.run_on_main()`. Never from background threads.
- **Default `media_strategy` to `"none"`** — require explicit opt-in.
- **Pre-operation backups** before any import/pull.
- **Wrap imports** in `col.db.begin()` / `.commit()` / `.rollback()`.
- **Match notes by nid**, notetypes by name.
- **Debounce auto-export** with 2s QTimer.

## Commands

```bash
uv run pytest tests/                         # all tests (needs anki/aqt installed)
uv run flake8 anki_git/ tests/               # lint
uv run python build.py all                   # clean → build → package .ankiaddon
uv run python scripts/release.py 0.2.0       # bump version, tag, push
```

## Quirks

- **Python ≥ 3.13** only.
- **Version in two places** — update both `pyproject.toml` AND `anki_git/__init__.py`.
- **`engine/importer.py`** scans for `notes.md` via rglob, but exporter writes `<nid>.md` per note — importer needs updating to match.
- **Menu:** "Sync" (two-way), "Export to Repo (Snapshot)" (one-way), "Import from Repo (Pull)" (one-way), "Settings..."
- **Flake8 only** — no typechecker. Config in `pyproject.toml`: max-line-length=100, ignores E501/W503.
- **CI ignores legacy files** that don't exist anymore: `--ignore=tests/test_ki.py --ignore=tests/test_integration.py --ignore=tests/test_package.py --ignore=tests/test_parser.py`.
- **License is AGPL-3.0** (not GPL as README says).
- **Fixtures** in `tests/conftest.py` provide `anki_session` (headless Anki) and `mock_aqt_mw`.
- **No pre-commit hooks, no codegen, no migrations.**
