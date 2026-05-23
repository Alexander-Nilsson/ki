# AnkiGit — Git Version Control for Anki

**AnkiGit** is an Anki addon that provides Git-based version control for your Anki collections. Export your collection to a human-readable Git repo, track every change, collaborate on decks, and roll back to any point in history.

Built on the foundation of [ki](https://github.com/langfield/ki) — reimagined as a proper Anki addon with a clean Qt UI, thread-safe collection access, and three-way merge conflict resolution.

## Status

Working MVP: **Take Snapshot** in Tools → AnkiGit, with progress feedback, per-note file export, and idempotent re-exports.

## Features

- **Snapshot** — export your entire collection to a Git repo (one Markdown file per note, YAML notetypes)
- **Incremental export** — only re-export changed notes since the last snapshot
- **Notetype tracking** — clean YAML export with CSS separated into its own file
- **Progress feedback** — animated progress bar with step-by-step status during export
- **Auto-sync** — debounced auto-export on note changes, snapshot on profile close
- **Import** — apply changes from your Git repo back into Anki (planned)
- **Conflict resolution** — three-way merge detection with a Qt dialog (planned)
- **Remote push** — push your repo to GitHub/GitLab (planned)

## Architecture

```
anki_git/
├── __init__.py          # Anki hook registration only
├── addon.py             # Qt UI: menus, dialogs, settings
├── engine/
│   ├── exporter.py      # Anki → files (read-only)
│   ├── importer.py      # files → Anki (write)
│   ├── git_ops.py       # GitPython operations
│   ├── conflict.py      # Three-way merge logic
│   └── checksums.py     # Content hashing
├── formats/
│   ├── notes_md.py      # Markdown parse/serialize
│   ├── notetype_yaml.py # YAML parse/serialize
│   └── media.py         # Media handling strategies
├── ui/
│   ├── settings.py      # Settings dialog
│   ├── conflicts.py     # Conflict resolution dialog
│   └── progress.py      # Progress bar widget
└── config.py            # Config schema + defaults
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
uv run flake8 ...          # lint
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

AGPL-3.0 — derived from [ki](https://github.com/langfield/ki).
