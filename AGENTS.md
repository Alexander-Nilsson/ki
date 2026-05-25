# AGENTS.md — AnkiGit

Anki addon providing Git-based version control for Anki collections. Export collections to a human-readable Git repo.

## Architecture

```
anki_git/
├── __init__.py          # Hook registration only; calls init_addon() on import
├── addon.py             # Qt UI: menus, dialogs, hook wiring
├── config.py            # KiSyncConfig dataclass (legacy naming from ki)
├── engine/              # NEVER import aqt here — must be testable without Anki
│   ├── exporter.py      # Anki→files (one-way snapshot; supports quick delta mode)
│   ├── importer.py      # files→Anki (one-way pull via conflict pipeline)
│   ├── sync.py          # Two-way sync: merge changes in both directions
│   ├── git_ops.py       # GitPython operations (incl. fetch_remote)
│   ├── conflict.py      # Three-way merge + auto-resolution by sync_mode
│   └── checksums.py     # meta.json hashing + quick_has_changes()
├── formats/
│   ├── notes_md.py      # One file per note: decks/<Deck>/<nid>.md
│   ├── notetype_yaml.py # notetypes/<Name>.yaml + <Name>.css
│   └── media.py
├── ui/
│   ├── settings.py      # Settings dialog (includes sync_mode selector)
│   ├── conflicts.py     # Conflict resolution dialog
│   ├── diff.py           # Diff preview dialog
│   └── history.py       # Commit history dialog
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
- **Auto-snapshot on close** uses `quick=True` (delta: only `mod > last_max_mod`) — fast.
- **Auto-sync on startup** uses `quick_has_changes()` first — instant skip if nothing changed. No mid-session auto-export.

## Commands

```bash
uv run pytest tests/                         # all tests (needs anki/aqt installed)
uv run pytest tests/ -m "not integration"    # engine-layer tests only
uv run ruff check anki_git/ tests/           # lint
uv run pyright anki_git/                     # type check (engine layer only)
uv run python build.py all                   # clean → build → package .ankiaddon
uv run python scripts/release.py 0.2.0       # bump version, tag, push
```

## Flows (Startup / Close)

**Startup (`on_profile_open`)**:
1. Show menu (once per session)
2. Fire-and-forget `git fetch` in daemon thread (non-blocking)
3. `quick_has_changes()` — 2 SQL queries + git status check (~5ms)
4. No changes → return silently (instant)
5. Changes detected → `_run_startup_import()`:
   - `QueryOp`: compute `compute_import_diff()` with progress dialog
   - `DiffDialog`: show changes, user accepts/rejects
   - Accepted → backup → `pull_from_repo()` → verification commit (`"Import N notes from repo"`) → push
   - Rejected → silent exit

**Close (`on_profile_close`)**:
1. Guard: repo exists, collection open
2. `quick_has_changes()` → no changes → return instantly
3. `export_collection(quick=True, remote_url=...)`:
   - Only processes notes where `mod > last_max_mod` (delta, not full walk)
   - Removes checksums for deleted notes
   - Commits + pushes to remote

## Quirks

- **Python ≥ 3.13** only.
- **Version in two places** — update both `pyproject.toml` AND `anki_git/__init__.py`.
- **`engine/importer.py`** uses `rglob("*.md")` which matches both `<nid>.md` and legacy `notes.md` — `parse_notes_file()` handles both formats.
- **Menu:** "Export to Repo" (Anki→Git), "Import from Repo" (Git→Anki), "View History", "Settings..."
- **Ruff + pyright** for static analysis. Config in `pyproject.toml`.
- **CI ignores legacy files** that don't exist anymore: `--ignore=tests/test_ki.py --ignore=tests/test_integration.py --ignore=tests/test_package.py --ignore=tests/test_parser.py`.
- **License is AGPL-3.0-only**.
- **Fixtures** in `tests/conftest.py` provide `anki_session` (headless Anki) and `mock_aqt_mw`.
- **Pre-commit hooks** available (`.pre-commit-config.yaml`).**
