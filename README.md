# AnkiGit — Git Version Control for Anki

**AnkiGit** is an Anki addon that provides Git-based version control for your Anki collections. Export your collection to a human-readable Git repo, track every change, collaborate on decks, and roll back to any point in history.

Built on the foundation of [ki](https://github.com/langfield/ki) — reimagined as a proper Anki addon with a clean Qt UI, thread-safe collection access, and three-way merge conflict resolution.

## Status

Under active development. MVP is a read-only snapshot tool (Tools > AnkiGit > Take Snapshot).

## Features (Roadmap)

- **Snapshot** — export your entire collection to a Git repo of Markdown notes + YAML notetypes
- **Incremental export** — only re-export changed notes since the last snapshot
- **Notetype tracking** — clean YAML export with CSS separated into its own file
- **Import** — apply changes from your Git repo back into Anki
- **Conflict resolution** — three-way merge detection with a Qt dialog for manual resolution
- **Auto-sync** — debounced export on note changes, snapshot on close
- **Remote push** — push your repo to GitHub/GitLab for backup or collaboration
- **Media handling** — opt-in strategies: none, symlink, copy, git-lfs

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

*Coming soon — installable via AnkiWeb or manually.*

## License

GPL — derived from [ki](https://github.com/langfield/ki).
