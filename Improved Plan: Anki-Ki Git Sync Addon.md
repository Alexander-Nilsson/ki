---
## Improved Plan: Anki-Ki Git Sync Addon
---

## Revised Phase Plan

### Phase 0: Research & Foundation (Week 1)

Before writing code, audit ki deeply. It assumes exclusive collection access via its own `Collection` open/close lifecycle. The addon must inject an already-open collection. Ki also uses `aiofiles` and has async patterns that conflict with Anki's Qt event loop. Document every place ki calls `col.close()` or `col.open()` — these all need to become no-ops or be patched.

**Deliverables:**
- Fork ki, strip the CLI entry points, map all collection-touching code
- Create the addon skeleton: `__init__.py`, `manifest.json`, `config.json`, `meta.json`
- Set up a dev collection with 500+ notes across 5+ notetypes for testing
- Establish the Git repo layout (see Architecture section below)

**Critical decision here:** Do you wrap ki or replace its core? Given ki's async architecture and CLI assumptions, consider using ki only for inspiration and writing a fresh export/import engine. Ki's value is its research into the Anki database format, not its code.

---

### Phase 1: Safe Read-Only Export Engine (Weeks 2–3)

Build the export engine first, with zero write access to the collection. This gives you something useful immediately (a snapshot tool) and lets you validate your file format before building the import side.

**Notetype YAML format** — this is the most important design decision. Each notetype gets its own file:

```yaml
# notetypes/Basic.yaml
name: Basic
id: 1234567890  # stored for reference, never used for import matching
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
    bqfmt: ""
    bafmt: ""
css: |
  .card {
    font-family: arial;
    font-size: 20px;
  }
sort_field: 0
type: 0  # 0=standard, 1=cloze
deck_presets: {}  # deck-specific option overrides
```

Key design choices here: match notetypes by **name**, not ID. IDs differ between machines; names are the human-meaningful identifier. Store the ID as a comment/reference only. Separate the CSS into its own file (`notetypes/Basic.css`) for clean diffs — CSS changes are the most common notetype edit and burying them inside YAML makes diffs ugly.

**Note Markdown format** — the most visible user-facing decision. Per-deck files, one note per section:

```markdown
<!-- note: nid=1234567890 notetype=Basic tags=japanese::vocab deck=Japanese::N5 -->
## Front
日本語

## Back
Japanese language

<!-- note: nid=9876543210 notetype=Cloze tags=math deck=Math::Calculus -->
## Text
The derivative of {{c1::sin(x)}} is {{c2::cos(x)}}
```

The HTML comment header is machine-readable without cluttering the visual. Each field gets an `##` heading. This gives beautiful diffs: changing a card's back field shows exactly one changed line. Avoid JSON frontmatter (ugly diffs) or custom delimiters (fragile parsing).

**Incremental export using mod timestamps:**

```python
def get_changed_notes(col, last_export_time: int) -> list[Note]:
    # Anki stores mod as Unix timestamp (seconds)
    return col.db.list(
        "SELECT id FROM notes WHERE mod > ?", last_export_time
    )
```

Store `last_export_time` in `.ki/meta.json` in the repo. On first export, export everything. Subsequently, only re-export notes where `mod > last_export_time`. For notetypes, check `col.models.all()` and compare against stored checksums.

**Performance on 50k+ collections:** Never load all notes into memory. Process in batches of 1000. Use `col.db.execute()` directly for bulk queries rather than the higher-level API which instantiates full `Note` objects for every row.

---

### Phase 2: Git Integration Layer (Week 3)

Use `GitPython` rather than shelling out to `git`. It's more reliable and gives you proper error handling.

**Repo structure:**
```
my-anki-repo/
├── .ki/
│   ├── meta.json          # last_export_time, collection_path, checksum
│   └── config.yaml        # user preferences
├── notetypes/
│   ├── Basic.yaml
│   ├── Basic.css
│   ├── Cloze.yaml
│   └── Cloze.css
├── decks/
│   ├── Japanese/
│   │   ├── N5/
│   │   │   └── notes.md
│   │   └── N4/
│   │       └── notes.md
│   └── Math/
│       └── Calculus/
│           └── notes.md
├── media/
│   └── (symlinked or copied media files)
└── .gitignore
```

**Critical: media handling.** Media files can be gigabytes. Add a `media_strategy` config option: `none` (ignore media), `symlink` (Unix only), `copy` (safe but large), `git-lfs` (best for large collections, requires git-lfs installed). Default to `none` with a clear warning. Never commit media without explicit user opt-in.

**Commit message format:**
```
snapshot: 47 notes changed, 2 notetypes updated

Changed decks: Japanese::N5 (23 notes), Math (24 notes)
Changed notetypes: Basic, Cloze
Collection: /Users/name/Library/Application Support/Anki2/User 1/collection.anki2
Timestamp: 2024-01-15T10:30:00Z
```

---

### Phase 3: Import Engine (Weeks 4–5)

This is the hardest phase. Build it conservatively.

**Matching strategy for notes:** Match by `nid` (note ID in the HTML comment header). If nid is present and exists in the collection → update. If nid is present but doesn't exist → this is a deleted note, skip or warn. If nid is absent → this is a new note, create it. Never match by content — too fragile.

**Matching strategy for notetypes:** Match by name. If name exists → update fields/templates/CSS, preserving the existing ID. If name doesn't exist → create new notetype. **Never rename a notetype through the file** — this is ambiguous (was it renamed, or is it a new type?). Treat a missing name as deletion and a new name as creation. Document this clearly.

**Field change safety:** If a notetype's fields change (reordered, renamed, or deleted), Anki normally asks the user to confirm because it's destructive. Before applying field changes, show a Qt dialog explaining what will change and requiring confirmation. Log all field changes to a file.

**Import transaction model:** Use Anki's `col.db.begin()` / `col.db.commit()` / `col.db.rollback()` to wrap the entire import. If anything fails mid-import, roll back completely. Never leave the collection in a partial state.

---

### Phase 4: Conflict Detection & Resolution (Week 5)

This is where most sync tools fail. Be conservative.

**The three-way merge problem:** You have:
- `base`: the last exported state (stored as checksums in `.ki/meta.json`)
- `local`: current Anki collection state
- `remote`: the Git repo state (potentially edited by another machine or by hand)

**Conflict cases:**
1. Note changed in Anki AND changed in Git → **conflict** — must ask user
2. Note changed only in Anki → Anki wins (push direction)
3. Note changed only in Git → Git wins (pull direction)
4. Note deleted in Anki, unchanged in Git → delete from Git
5. Note deleted in Git, unchanged in Anki → delete from Anki (with confirmation)
6. Note deleted in both → fine, already gone

**Store checksums, not full content:** In `.ki/meta.json`, store `{nid: md5(content)}` for every exported note. This lets you detect three-way conflicts without storing the full content twice.

**UI for conflicts:** A Qt dialog listing conflicted notes with three options per conflict: "Keep Anki version", "Keep Git version", "Skip this note". Provide a "Keep all Anki" and "Keep all Git" bulk option. Log all conflict resolutions.

**The nuclear option:** Always provide a "backup and replace" option that backs up the collection to a timestamped `.anki2` file, then applies the Git state wholesale. Some users just want their Git repo to win, always.

---

### Phase 5: Anki Hook Integration (Week 6)

Now that the core engine is solid, wire it to Anki events.

**Hooks to use:**
```python
from aqt import gui_hooks

# On startup — pull first, then export
gui_hooks.profile_did_open.append(on_profile_open)

# On note changes — debounced batch export
gui_hooks.note_will_flush.append(on_note_change)

# On notetype changes
gui_hooks.models_will_rem.append(on_model_remove)
# (no hook for model edit completion — use a QTimer polling approach)

# On close — final snapshot
gui_hooks.profile_will_close.append(on_profile_close)

# On sync complete (after Anki's own sync)
gui_hooks.sync_did_finish.append(on_anki_sync_complete)
```

**Debouncing is essential.** Adding 50 notes via import triggers 50 `note_will_flush` calls. Use a `QTimer` with a 2-second delay that resets on each event. Only run the export when the timer fires without being reset.

```python
_export_timer = None

def on_note_change(note):
    global _export_timer
    if _export_timer:
        _export_timer.stop()
    _export_timer = QTimer()
    _export_timer.setSingleShot(True)
    _export_timer.timeout.connect(run_incremental_export)
    _export_timer.start(2000)  # 2 second debounce
```

**Never block the main thread.** All git operations, file I/O, and export work must run in a `QThread`. Show a subtle progress indicator in the status bar (not a blocking dialog) for long operations.

---

### Phase 6: Settings UI & Configuration (Week 7)

**Settings dialog** (accessible via Tools > ki Sync > Settings):
- Repository path (with Browse button)
- Auto-sync on startup: toggle
- Auto-snapshot on close: toggle  
- Debounce delay: slider (500ms–10s)
- Media strategy: dropdown (none/symlink/copy/git-lfs)
- Remote URL: text field (for `git push` after snapshot)
- Auto-push after snapshot: toggle
- Log level: dropdown (Error/Warning/Info/Debug)

**Config stored in Anki's `addonManager.getConfig()`** — not in the Git repo, since the repo may be shared but config is per-machine.

---

### Phase 7: Safety, Logging & Polish (Week 8)

- **Pre-operation backups:** Before any import/pull operation, copy the collection to `~/.ki/backups/collection_TIMESTAMP.anki2`. Keep the last 5 backups. This is non-negotiable.
- **Structured logging:** Write to `~/.ki/logs/ki_YYYY-MM-DD.log` with rotation. Include operation type, duration, note counts, any errors.
- **Dry-run mode:** All import operations support `--dry-run` / a "Preview changes" button that shows what would change without applying anything.
- **Health checks:** On startup, verify the repo is a valid git repo, the collection path matches, and there are no uncommitted merge conflicts.
- **Clear error messages:** Catch specific exceptions (`GitCommandError`, `sqlite3.OperationalError`, etc.) and show user-friendly messages with suggested fixes.

---

## Architecture Improvements

**Separation of concerns:**
```
ki_addon/
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

**Key architectural principle:** The `engine/` layer must never import from `aqt` — only from `anki`. This makes the engine testable without a running Anki instance. The `addon.py` and `ui/` layers handle all Qt dependencies.

---

## Additional Features Worth Adding

**Multi-profile support:** Anki supports multiple profiles (different users on the same machine). Each profile should get its own repo or repo branch. Store the profile name in `.ki/meta.json` and warn if the profile doesn't match.

**Branch-per-device workflow:** For users syncing across machines, support a mode where each machine commits to its own branch (`device/laptop`, `device/desktop`) and uses `git merge` for reconciliation. This sidesteps most conflict scenarios.

**Notetype version history queries:** A UI panel that shows "this notetype was last changed 3 commits ago, here's what changed" using `git log -p notetypes/Basic.yaml`.

**Selective export:** Allow exporting only specific decks (configured in settings). On 50k+ collections, users may only care about tracking one deck in Git.

**`.gitattributes` generation:** Auto-generate a `.gitattributes` that marks `*.md` files as using LF line endings and enables proper diff display for Markdown.

---

## Risks & Mitigations

**Anki database locking:** SQLite's WAL mode means reads are safe concurrently, but writes require exclusive access. Never write to the collection from a background thread. All collection writes must happen on Anki's main thread via `mw.taskman.run_on_main()`.

**Collection schema changes between Anki versions:** Anki's internal DB schema changes between major versions. Pin to a minimum Anki version (2.1.55+) and test on each major release. Wrap all direct DB queries in try/except and fall back to the public API if a query fails.

**Large media collections:** A user with 10GB of audio files can accidentally commit all of it. Default `media_strategy` to `none`, require explicit opt-in, and add a pre-commit check that warns if media would exceed 100MB.

**Git not installed:** GitPython requires git. Check for git on addon load and show a clear error with installation instructions if missing. On Windows, bundle a minimal git or detect Git for Windows.

**ki's GPL license:** Ki is GPL-licensed. Since you're forking and distributing it, your addon must also be GPL. If you want a different license, write the core engine from scratch using ki only as a reference.

**Encoding issues:** Anki stores all content as UTF-8, but Windows git may use different line endings. Always open files with `encoding='utf-8', newline='\n'` and ensure `.gitattributes` enforces LF.

---

## MVP Priority

For a first useful release, build in this order:

1. **Read-only snapshot** (Phase 1 + 2, export only): export the collection to a Git repo with one command. No import, no automation. This alone is valuable.
2. **Menu integration** (Phase 5 menu only, no hooks): Tools > ki Sync > Take Snapshot
3. **Notetype tracking**: ensure notetypes export cleanly with CSS separated
4. **Manual push to remote**: add "Push to Remote" menu item
5. **Settings dialog**: just repo path + manual snapshot button

Then iterate: add incremental export, then import, then automation, then conflict resolution. Each step is independently useful and testable.---

## Summary of Key Improvements Over the Original Plan

The most important changes to the original plan:

**Reordered priorities.** The original buries the file format design in Phase 2. It's actually the most consequential decision — get it wrong and every subsequent phase builds on a broken foundation. Design the Markdown and YAML schemas first, validate them with real diffs, then build the engines around them.

**Replaced ki wholesale.** Ki's CLI-first, async architecture makes it harder to adapt than to replace. Use it as a reference for Anki DB structure, but write a fresh engine. The GPL licensing also forces your hand — if you're forking ki you're GPL anyway, so you might as well own the code.

**Added three-way merge.** The original's "basic conflict detection" is wildly underspecified. Without checksums of the last exported state, you can't distinguish "changed in Anki" from "changed in Git" from "changed in both". The checksum approach in `.ki/meta.json` solves this cleanly.

**Made safety non-negotiable.** Pre-operation backups, transaction rollback on import failure, and dry-run mode should be in the MVP, not polished in later. A bug in Phase 3 that corrupts someone's collection will destroy trust in the project instantly.

**Thread model is explicit.** The original doesn't address Qt's main thread requirement at all. Every collection write must happen on the main thread; every long operation must happen off it. Getting this wrong causes either UI freezes or SQLite errors that are hard to debug.
