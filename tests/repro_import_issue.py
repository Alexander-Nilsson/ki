
import os
from pathlib import Path

import pytest

from anki_git.engine.diff import compute_import_diff
from anki_git.engine.exporter import export_collection
from anki_git.formats.notes_md import Note, parse_notes_file


def test_repro_import_detection(anki_session):
    col = anki_session.collection
    repo_path = Path(anki_session.base) / "repo"
    repo_path.mkdir()

    # 1. Create a note in Anki
    m = col.models.by_name("Basic")
    note = col.new_note(m)
    note.fields[0] = "Front"
    note.fields[1] = "Back"
    col.add_note(note, col.decks.id("Default"))
    nid = note.id

    # 2. Export to repo
    export_collection(col, repo_path)

    # 3. Verify it's there
    md_file = repo_path / "decks" / "Default" / f"{nid}.md"
    assert md_file.exists()

    # 4. Modify the note in repo
    notes = parse_notes_file(md_file)
    assert len(notes) == 1
    notes[0].fields["Front"] = "Modified Front"
    md_file.write_text(notes[0].serialize(), encoding="utf-8")

    # 5. Check if diff detects it
    report = compute_import_diff(col, repo_path)
    assert report.has_changes, "Diff should detect note changes"
    assert len(report.note_diffs) == 1
    assert report.note_diffs[0].change_type == "modified"

    # 6. Modify ONLY a template in a notetype in repo
    from anki_git.formats.notetype_yaml import read_all_notetypes, write_notetype
    nt_dir = repo_path / "notetypes"
    nt_dict = read_all_notetypes(nt_dir)
    basic_nt = nt_dict["Basic"]
    basic_nt.templates[0].qfmt += " <!-- modified -->"
    write_notetype(nt_dir, basic_nt)

    # 7. Check if diff detects it
    report = compute_import_diff(col, repo_path)
    assert report.has_changes, "Should detect template change"
    assert any(ntd.name == "Basic" for ntd in report.notetype_diffs)

    # 8. Create a new note in repo
    from anki_git.formats.notes_md import write_note_file
    new_note = Note(nid=999, notetype="Basic", tags=[], deck="Default", fields={"Front": "New", "Back": "Note"})
    write_note_file(repo_path / "decks" / "Default", new_note)

    # 9. Check if diff detects it
    report = compute_import_diff(col, repo_path)
    assert report.has_changes
    assert any(nd.nid == 999 for nd in report.note_diffs)

if __name__ == "__main__":
    # This is just for local testing if needed
    pass
