# AnkiGit — Architecture

## Complexity Notes

- **3 parallel data paths (export / import / sync) with ~40% duplicated logic** — each independently walks notes, notetypes, and checksums. `import_helpers.py` extracts shared import code, but no symmetric `export_helpers.py` exists.
- **Conflict system over-factored** — `detect_conflicts()` → `resolve_conflicts()` → `enrich_conflicts_with_content()` are always called sequentially; could be one function. `resolve_conflicts` and `merge_notetypes` duplicate the same 4-mode resolution logic for different structures.
- **Threading boilerplate repeated 4×** — `threading.Event()` + `mw.taskman.run_on_main()` for conflict and preview callbacks appears identically in sync, import, and startup-sync.
- **`meta.json` written twice per sync** — once for checksums, once for tracking metadata. Single write suffices.

---

## 1. Architecture

```mermaid
flowchart TB
    subgraph AnkiApp["Anki"]
        MW["aqt (Main Window)"]
        COL["Anki Collection"]
        HOOKS["gui_hooks"]
    end

    subgraph UI["anki_git/ui/"]
        CONFLICT_DLG["ConflictResolutionDialog"]
        DIFF_DLG["DiffDialog"]
        SETTINGS["SettingsDialog"]
    end

    subgraph ENTRY["anki_git/"]
        ADDON["addon.py (menu + hooks)"]
        CONFIG["config.py (KiSyncConfig)"]
    end

    subgraph ENGINE["anki_git/engine/ (no aqt!)"]
        EXP["exporter.py (one-way Anki→Git)"]
        IMP["importer.py (one-way Git→Anki)"]
        SYNC["sync.py (two-way)"]
        CONF["conflict.py (3-way detection + merge)"]
        DIFF["diff.py (field-level diff)"]
        CHK["checksums.py (md5 + meta.json)"]
        GIT["git_ops.py (GitPython)"]
        IMPH["import_helpers.py"]
    end

    subgraph FMT["anki_git/formats/"]
        NOTES_MD["notes_md.py (<nid>.md)"]
        NT_YAML["notetype_yaml.py (notetype dirs)"]
        MEDIA["media.py (symlink/copy/lfs)"]
    end

    subgraph REPO["Git Repo"]
        DECKS["decks/<Deck>/<nid>.md"]
        NTYPES["notetypes/<Name>/"]
        META[".ki/meta.json"]
    end

    HOOKS --> ADDON
    ADDON --> SYNC & EXP & IMP & SETTINGS & DIFF_DLG & CONFLICT_DLG
    SYNC --> CONF & CHK & GIT & IMPH & NOTES_MD & NT_YAML
    EXP --> CHK & GIT & NOTES_MD & NT_YAML & MEDIA & IMPH
    IMP --> CHK & CONF & IMPH & NOTES_MD & NT_YAML
    DIFF --> NOTES_MD & NT_YAML
    NOTES_MD --> DECKS
    NT_YAML --> NTYPES
    CHK -.-> META
    GIT -.-> DECKS & NTYPES
    ADDON -.-> CONFIG & COL
    SYNC & EXP & IMP -.-> COL
```

## 2. Core Flow

```mermaid
flowchart LR
    subgraph Export["One-Way Export"]
        direction TB
        E1["Open repo"] --> E2["Load meta.json (old checksums)"]
        E2 --> E3["Walk all notes → compute new checksums"]
        E3 --> E4["Write changed <nid>.md + notetypes"]
        E4 --> E5["Clean stale repo files"]
        E5 --> E6["Update meta.json → git commit"]
        E6 --> E7["Push (optional)"]
    end

    subgraph Import["One-Way Import"]
        direction TB
        I1["Load base checksums"] --> I2["Compute anki + git checksums"]
        I2 --> I3["detect_conflicts() (3-way)"]
        I3 --> I4["Resolve / prompt user"]
        I4 --> I5["Apply git-winning notes to Anki"]
        I5 --> I6["Delete resolved notes from both sides"]
        I6 --> I7["Import notetypes → update meta.json"]
    end

    subgraph Sync["Two-Way Sync"]
        direction TB
        S1["Load base checksums"] --> S2["Compute anki + git checksums"]
        S2 --> S3["detect_conflicts()"]
        S3 --> S4["resolve_conflicts() by sync_mode"]
        S4 --> S5["enrich conflicts with content"]
        S5 --> S6{"True conflicts + always_ask?"}
        S6 -->|Yes| S7["Conflict dialog"]
        S6 -->|No| S8
        S7 --> S8["Import (repo→Anki)"]
        S8 --> S9["Export (Anki→repo)"]
        S9 --> S10["Merge notetypes bi-directional"]
        S10 --> S11["Update checksums → commit → push"]
    end

    Export ~~~ Import ~~~ Sync

    style S10 stroke:#e74c3c,stroke-dasharray:5 5
    style I2 stroke:#f39c12,stroke-dasharray:5 5
    note placement="left" style S10 stroke:red,stroke-dasharray:5 5
```

## 3. Key Sequence: Two-Way Sync

```mermaid
sequenceDiagram
    participant U as User
    participant MW as Main Window
    participant COL as Anki Collection
    participant ADDON as addon.py
    participant SYNC as sync.py
    participant CONFL as conflict.py
    participant IMPH as import_helpers.py
    participant GIT as git_ops.py
    participant UI as ui/conflicts.py
    participant REPO as Git Repo

    U->>MW: Tools → AnkiGit → Sync
    MW->>ADDON: sync_action()
    ADDON->>SYNC: sync_collection() (background QueryOp)
    SYNC->>GIT: get_or_init_repo()
    SYNC->>IMPH: compute_anki_checksums() + compute_git_checksums()
    SYNC->>CONFL: detect_conflicts(base, anki, git) → ConflictReport
    SYNC->>CONFL: resolve_conflicts(report, sync_mode)

    alt always_ask + conflicts
        SYNC->>UI: ConflictResolutionDialog (thread sync via Event)
        UI->>U: Show side-by-side field comparison
        U->>UI: Resolve per-note or bulk
        UI-->>SYNC: resolved Report
    end

    SYNC->>SYNC: Import repo→Anki, Export Anki→repo
    SYNC->>CONFL: merge_notetypes() bi-directional
    SYNC->>GIT: stage_files() → commit() → push() (optional)
    SYNC-->>MW: SyncResult
    MW-->>U: Summary dialog
```

## 4. Data Flow

```mermaid
flowchart LR
    ANKI[("Anki Collection")] -->|Notes + Notetypes| CHK_A["anki_checksums {nid: md5}"]
    REPO[("Git Repo")] -->|Parse files| CHK_G["git_checksums {nid: md5}"]
    META[".ki/meta.json"] -->|Load| CHK_B["base_checksums {nid: md5}"]

    CHK_B & CHK_A & CHK_G --> DETECT["detect_conflicts()"]
    DETECT --> REPORT["ConflictReport"]
    REPORT --> RESOLVE["resolve_conflicts()"]
    RESOLVE --> APPLY["Apply mutations"]
    APPLY -->|write_note_file| REPO
    APPLY -->|import_notes| ANKI
    APPLY -->|write_notetype| REPO
    APPLY -->|import_notetype| ANKI
    ANKI -->|export_collection| REPO
    REPO -->|import_from_repo| ANKI

    REPORT -.->|enrich + dialog| CONFLICT_DLG["ConflictResolutionDialog"]
    ANKI -.-> DIFF_ENG["diff.py (DiffReport)"]
    REPO -.-> DIFF_ENG
    DIFF_ENG -.-> DIFF_DLG["DiffDialog (preview)"]
```

### File format summary

| Path | Format |
|------|--------|
| `decks/<Deck>/<nid>.md` | `<!-- note: nid=N notetype=X tags=Y deck=Z -->` + `## FieldName` sections |
| `notetypes/<Name>/meta.json` | `{name, id, sort_field}` |
| `notetypes/<Name>/fields.json` | `[{name, ord, font?, size?, ...}]` |
| `notetypes/<Name>/templates.json` | `[{name, ord}]` + `front.html` / `back.html` per card |
| `notetypes/<Name>/style.css` | Plain CSS |
| `.ki/meta.json` | `{note_checksums, last_export_time, last_note_count, ...}` |
