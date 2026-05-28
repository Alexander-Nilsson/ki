# AnkiGit — Git Version Control for Anki

**AnkiGit** is an Anki addon that provides Git-based version control for your Anki collections. Export your collection to a human-readable Git repo, track every change, collaborate on decks, and roll back to any point in history.

## Features

- **Export** — snapshot your collection to a Git repo (one Markdown file per note, YAML notetypes)
- **Incremental export** — only re-export changed notes since the last snapshot
- **Import** — apply changes from your Git repo back into Anki
- **Selective import** — pick individual notes and notetypes to import via checkboxes
- **Diff preview** — git-style diff viewer before export/import
- **Conflict resolution** — three-way merge detection with a Qt dialog and auto-resolve modes
- **Notetype tracking** — clean YAML export with CSS separated into its own file
- **Auto-import on startup** — automatically check for repo changes when Anki opens
- **Auto-snapshot on close** — snapshot changes when Anki closes
- **Remote push** — auto-push to GitHub/GitLab after snapshot
- **Progress feedback** — animated progress bar with step-by-step status during operations

## Architecture

```
anki_git/
├── __init__.py          # Hook registration only; calls init_addon()
├── addon.py             # Qt UI: menus, dialogs, hook wiring
├── config.py            # AnkiGitConfig dataclass + SyncMode enum
├── engine/              # No aqt dependency — testable without Anki
│   ├── exporter.py      # Anki → files (one-way snapshot)
│   ├── importer.py      # files → Anki (one-way pull)
│   ├── git_ops.py       # GitPython operations
│   ├── conflict.py      # Three-way merge + auto-resolution
│   ├── checksums.py     # meta.json hashing + change detection
│   ├── diff.py          # Diff computation (delta-based)
│   ├── export_helpers.py# Shared export helpers
│   ├── import_helpers.py# Shared import helpers
│   └── constants.py     # Path constants
├── formats/
│   ├── notes_md.py      # Markdown parse/serialize (<nid>.md)
│   ├── notetype_yaml.py # YAML parse/serialize (notetypes)
│   └── media.py         # Media handling strategies
└── ui/
    ├── settings.py      # Settings dialog (includes sync_mode selector)
    ├── conflicts.py     # Conflict resolution dialog
    ├── diff.py          # Diff preview dialog
    └── utils.py         # Shared UI utilities (run_on_main_sync)
```

## Installation

### From source (development)

```bash
git clone <repo-url>
ln -s "$(pwd)/anki_git/anki_git" ~/.local/share/Anki2/addons21/anki_git
```

### uv (for development without Anki)

```bash
uv sync                    # create venv + install deps
uv run pytest ...          # run tests
```

### Building

```bash
python3 build.py all       # creates .ankiaddon in build/
```

## Development

```bash
uv run pytest tests/ -m "not integration"   # engine-layer tests only
uv run pytest tests/                         # all tests (needs anki/aqt)
uv run ruff check anki_git/ tests/           # lint
uv run pyright anki_git/                     # type check (engine layer)
```

## License

AGPL-3.0-only
