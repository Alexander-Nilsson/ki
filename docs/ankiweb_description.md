AnkiGit provides Git-based version control for your Anki collections. Export your collection to a human-readable Git repo, track every change, collaborate on decks, and roll back to any point in history.

## How It Works

AnkiGit exports every note as a standalone Markdown file inside a local Git repository. Snapshots happen on demand or automatically on close — each commit records the full state of your collection in human-readable form.

| Diff Preview | Settings |
|---|---|
| ![Diff UI](https://raw.githubusercontent.com/alexpdev/anki_git/main/docs/diffUI.png) | ![Config UI](https://raw.githubusercontent.com/alexpdev/anki_git/main/docs/configUI.png) |

## Features

- **Export** — snapshot your collection to a Git repo (one Markdown file per note)
- **Incremental export** — only re-export changed notes since the last snapshot
- **Import** — apply changes from your Git repo back into Anki
- **Selective import** — pick individual notes and notetypes via checkboxes
- **Diff preview** — git-style diff viewer before export/import
- **Conflict resolution** — three-way merge detection with a Qt dialog and auto-resolve modes
- **Notetype tracking** — clean YAML export with CSS separated into its own file
- **Auto-import on startup** — automatically check for repo changes when Anki opens
- **Auto-snapshot on close** — snapshot changes when Anki closes
- **Remote push** — auto-push to GitHub/GitLab after snapshot

### Example Note Format

Each note becomes `decks/<DeckName>/<nid>.md`:

```markdown
# Note
guid: dc6H$t-~MK
notetype: iKnow! Sentences

### Tags
languages
japanese
jp-sentences
jp-transportation

## Expression
駅からはタクシーに<b>乗って</b>ください。

## Meaning
Please take a taxi from the station.
乗る -- ride, take

## Reading
えき からは たくしー に <b>のって</b> ください

## Audio
[sound:e3c984736d8b1c2bdc467f2a1c98659a.mp3]

## Image_URI
<img src="e2d8a60b59f2be8ebcbffafa165c7a0d.jpg">

## iKnowID
sentence:247153

## iKnowType
sentence
```

### Quick Install

**Anki Code:** `1384407975`

### From source

```bash
git clone https://github.com/alexpdev/anki_git
ln -s "$(pwd)/anki_git/anki_git" ~/.local/share/Anki2/addons21/anki_git
```

---

[Source Code](https://github.com/alexpdev/anki_git) | AGPL-3.0-only
