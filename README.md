# AnkiGit — Git Version Control for Anki

**AnkiGit** is an Anki addon that provides Git-based version control for your Anki collections. Export your collection to a human-readable Git repo, track every change, collaborate on decks, and roll back to any point in history.

Built on the foundation of [ki](https://github.com/langfield/ki) — reimagined as a proper Anki addon with a clean Qt UI, thread-safe collection access, and three-way merge conflict resolution.

## Features

- **Snapshot** — export your entire collection to a Git repo (one Markdown file per note, YAML notetypes)
- **Incremental export** — only re-export changed notes since the last snapshot
- **Two-way sync** — bi-directional sync between Anki and repo with change detection
- **Import** — apply changes from your Git repo back into Anki
- **Conflict resolution** — three-way merge detection with a Qt dialog and auto-resolve modes
- **Notetype tracking** — clean YAML export with CSS separated into its own file
- **Progress feedback** — animated progress bar with step-by-step status during operations
- **Auto-sync on startup** — automatically check for repo changes when Anki opens
- **Auto-snapshot on close** — snapshot changes when Anki closes
- **Background mode** — silent operation without dialogs for automated workflows
- **Remote push** — auto-push to GitHub/GitLab after snapshot
- **Diff preview** — git-style diff viewer before export/import

## Architecture

```
anki_git/
├── __init__.py          # Anki hook registration only
├── addon.py             # Qt UI: menus, dialogs, settings
├── config.py            # Config schema + defaults
├── engine/
│   ├── exporter.py      # Anki → files (read-only)
│   ├── importer.py      # files → Anki (write)
│   ├── sync.py          # Two-way sync engine
│   ├── git_ops.py       # GitPython operations
│   ├── conflict.py      # Three-way merge logic
│   ├── checksums.py     # Content hashing
│   ├── export_helpers.py# Shared export helpers
│   └── import_helpers.py# Shared import helpers
├── formats/
│   ├── notes_md.py      # Markdown parse/serialize
│   ├── notetype_yaml.py # YAML parse/serialize
│   └── media.py         # Media handling strategies
└── ui/
    ├── settings.py      # Settings dialog
    ├── conflicts.py     # Conflict resolution dialog
    ├── diff.py          # Diff preview dialog
    └── utils.py         # Shared UI utilities
```

## Installation

### From source (development)

```bash
# Clone the repo and symlink into Anki's addons directory
git clone https://github.com/your-username/anki_git
ln -s "$(pwd)/anki_git/anki_git" ~/.local/share/Anki2/addons21/anki_git
```

### uv (for development without Anki)

```bash
uv sync                    # create venv + install deps
uv run pytest ...          # run tests
uv run ruff check ...      # lint
```

### Building

```bash
python3 build.py all       # creates .ankiaddon in build/
```

## Development

```bash
uv run pytest tests/ -m "not integration"   # engine-layer tests only
python3 -m pytest tests/                     # all tests (needs anki/aqt)
```

## License

AGPL-3.0-only — derived from [ki](https://github.com/langfield/ki).
