# AGENTS.md — AnkiGit Anki Addon

## Project Overview

This project is transitioning from `ki` (a CLI tool that converts Anki collections to Git repos) into **AnkiGit** — an Anki addon that provides Git-based version control for Anki collections directly inside the Anki UI.

## Architecture

```
anki_git/
├── __init__.py          # Anki hook registration only
├── addon.py             # Qt UI: menus, dialogs, settings
├── engine/
│   ├── exporter.py      # Anki → files (read-only collection access)
│   ├── importer.py      # files → Anki (write collection access)
│   ├── git_ops.py       # All git operations via GitPython
│   ├── conflict.py      # Three-way merge logic
│   └── checksums.py     # Content hashing utilities
├── formats/
│   ├── notes_md.py      # Markdown parse/serialize for notes
│   ├── notetype_yaml.py # YAML parse/serialize for notetypes
│   └── media.py         # Media file handling strategies
├── ui/
│   ├── settings.py      # Settings dialog
│   ├── conflicts.py     # Conflict resolution dialog
│   └── progress.py      # Progress bar widget
└── config.py            # Config schema + defaults
```

**Key principle**: The `engine/` layer must never import from `aqt` — only from `anki`. This makes the engine testable without a running Anki instance. The `addon.py` and `ui/` layers handle all Qt dependencies.

## File Formats

### Notetypes (`notetypes/<Name>.yaml` + `notetypes/<Name>.css`)
- Match notetypes by **name**, not ID
- Store ID only as reference
- CSS separated into its own file for clean diffs

```yaml
name: Basic
id: 1234567890
fields:
  - name: Front
    ord: 0
    font: Arial
    size: 20
    sticky: false
  - name: Back
    ord: 1
    font: Arial
    size: 20
    sticky: false
templates:
  - name: Card 1
    ord: 0
    qfmt: "{{Front}}"
    afmt: "{{FrontSide}}\n\n<hr id=answer>\n\n{{Back}}"
css: |
  .card { font-family: arial; font-size: 20px; }
sort_field: 0
type: 0
```

### Notes (`decks/<Deck>/notes.md`)
- One file per deck, one note per section
- HTML comment header is machine-readable without cluttering visual
- Each field gets an `##` heading

```markdown
<!-- note: nid=1234567890 notetype=Basic tags=japanese::vocab deck=Japanese::N5 -->
## Front
日本語

## Back
Japanese language
```

## MVP Priority

1. **Read-only snapshot** — export collection to Git repo
2. **Menu integration** — Tools > AnkiGit > Take Snapshot
3. **Notetype tracking** — clean YAML + CSS export
4. **Manual push to remote**
5. **Settings dialog** — repo path + snapshot button
6. Incremental export → import → automation → conflict resolution

## Critical Constraints

- Never write to the collection from a background thread. All collection writes must happen on Anki's main thread via `mw.taskman.run_on_main()`.
- Default `media_strategy` to `none` — require explicit opt-in.
- Pre-operation backups before any import/pull.
- Use Anki's `col.db.begin()` / `col.db.commit()` / `col.db.rollback()` to wrap imports.
- Match notes by `nid`, notetypes by name.
- Debounce export with 2-second `QTimer` on note changes.
- Thread safety: git/file I/O in `QThread`, collection writes on main thread.

## Git Repo Structure

```
my-anki-repo/
├── .ki/
│   ├── meta.json       # last_export_time, collection_path, checksums
│   └── config.yaml     # user preferences
├── notetypes/
│   ├── Basic.yaml
│   ├── Basic.css
│   └── ...
├── decks/
│   ├── Japanese/
│   │   └── N5/
│   │       └── notes.md
│   └── ...
├── media/              # symlinked or copied
└── .gitignore
```

## Commit Messages

```
snapshot: 47 notes changed, 2 notetypes updated

Changed decks: Japanese::N5 (23 notes), Math (24 notes)
Changed notetypes: Basic, Cloze
Collection: /path/to/collection.anki2
Timestamp: 2024-01-15T10:30:00Z
```

## Three-Way Merge Conflict Detection

Store `{nid: md5(content)}` in `.ki/meta.json` for every exported note:
1. Note changed in Anki AND in Git → conflict (ask user)
2. Changed only in Anki → Anki wins
3. Changed only in Git → Git wins
4. Deleted in Anki, unchanged in Git → delete from Git
5. Deleted in Git, unchanged in Anki → delete from Anki (with confirmation)

## Testing

Use `pytest`. Tests live in `tests/`. The engine layer must be testable without a running Anki instance. Use a dev collection with 500+ notes across 5+ notetypes.
