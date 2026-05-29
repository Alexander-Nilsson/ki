"""Tests for the import engine."""

import pytest

from anki_git.engine.import_helpers import compute_git_checksums
from anki_git.engine.importer import (
    ImportResult,
    preview_import,
)


def test_preview_import_no_repo(tmp_path):
    result = preview_import(tmp_path / "nonexistent")
    assert isinstance(result, ImportResult)
    assert result.notetypes_created == 0
    assert result.notes_created == 0


def test_preview_import_empty_repo(tmp_path):
    notetypes_dir = tmp_path / "notetypes"
    notetypes_dir.mkdir(parents=True)
    decks_dir = tmp_path / "decks"
    decks_dir.mkdir(parents=True)
    result = preview_import(tmp_path)
    assert result.notetypes_created == 0
    assert result.notes_created == 0


def test_preview_import_counts_notes(tmp_path):
    decks_dir = tmp_path / "decks" / "Default"
    decks_dir.mkdir(parents=True)
    note_file = decks_dir / "123.md"
    note_file.write_text(
        '<!-- note: nid=123 notetype=Basic tags=tag1 deck=Default -->\n## Front\nHello\n',
        encoding="utf-8",
    )
    result = preview_import(tmp_path)
    assert result.notes_created == 1


def test_preview_import_counts_notetypes(tmp_path):
    import json
    notetypes_root = tmp_path / "notetypes"
    nt_dir = notetypes_root / "Basic"
    nt_dir.mkdir(parents=True)
    (nt_dir / "meta.json").write_text(json.dumps({"name": "Basic", "id": 1}), encoding="utf-8")
    (nt_dir / "fields.json").write_text("[]", encoding="utf-8")
    result = preview_import(tmp_path)
    assert result.notetypes_created == 1


def test_compute_git_checksums(tmp_path):
    decks_dir = tmp_path / "decks" / "Default"
    decks_dir.mkdir(parents=True)
    note_file = decks_dir / "123.md"
    note_file.write_text(
        '<!-- note: nid=123 notetype=Basic tags=tag1 deck=Default -->\n## Front\nHello\n',
        encoding="utf-8",
    )
    checksums, notes = compute_git_checksums(tmp_path)
    assert "123" in checksums
    assert isinstance(checksums["123"], str)
    assert len(checksums["123"]) == 32
    assert 123 in notes


def test_import_result_defaults():
    r = ImportResult()
    assert r.notes_updated == 0
    assert r.notes_created == 0
    assert r.notetypes_updated == 0
    assert r.notetypes_created == 0
    assert r.errors == []
    assert r.warnings == []
    assert r.conflict_report is None


# --- Malformed data tests ---

def test_preview_import_malformed_nid(tmp_path):
    """A note with non-digit nid is silently skipped by preview_import."""
    decks_dir = tmp_path / "decks" / "Default"
    decks_dir.mkdir(parents=True)
    note_file = decks_dir / "123.md"
    note_file.write_text(
        '<!-- note: nid=abc notetype=Basic tags=tag1 deck=Default -->\n## Front\nHello\n',
        encoding="utf-8",
    )
    result = preview_import(tmp_path)
    assert result.notes_created == 0


def test_preview_import_no_header(tmp_path):
    """A file with no valid note header should yield 0 notes."""
    decks_dir = tmp_path / "decks" / "Default"
    decks_dir.mkdir(parents=True)
    note_file = decks_dir / "123.md"
    note_file.write_text(
        '# Just a heading\n\nSome random markdown with no proper header\n',
        encoding="utf-8",
    )
    result = preview_import(tmp_path)
    assert result.notes_created == 0


def test_preview_import_mixed_valid_invalid(tmp_path):
    """Valid notes count even if there are malformed files in the same repo."""
    decks_dir = tmp_path / "decks" / "Default"
    decks_dir.mkdir(parents=True)

    # Valid note
    (decks_dir / "1.md").write_text(
        '<!-- note: nid=1 notetype=Basic tags=tag1 deck=Default -->\n## Front\nValid\n',
        encoding="utf-8",
    )
    # Malformed note (missing notetype)
    (decks_dir / "2.md").write_text(
        '<!-- note: nid=2 tags=tag1 deck=Default -->\n## Front\nBad\n',
        encoding="utf-8",
    )
    # Another valid note
    (decks_dir / "3.md").write_text(
        '<!-- note: nid=3 notetype=Basic tags=tag2 deck=Default -->\n## Front\nAlso valid\n',
        encoding="utf-8",
    )

    result = preview_import(tmp_path)
    assert result.notes_created == 2


def test_preview_import_empty_note_file(tmp_path):
    """An empty .md file in the decks dir contributes 0 notes."""
    decks_dir = tmp_path / "decks" / "Default"
    decks_dir.mkdir(parents=True)
    (decks_dir / "empty.md").write_text("", encoding="utf-8")
    result = preview_import(tmp_path)
    assert result.notes_created == 0


def test_preview_import_non_md_files_ignored(tmp_path):
    """Files without .md extension in the decks dir are ignored by rglob('*.md')."""
    decks_dir = tmp_path / "decks" / "Default"
    decks_dir.mkdir(parents=True)
    (decks_dir / "note.txt").write_text("some content", encoding="utf-8")
    (decks_dir / "note.json").write_text("{}", encoding="utf-8")
    result = preview_import(tmp_path)
    assert result.notes_created == 0


def test_preview_import_unclosed_comment(tmp_path):
    """A note with unclosed HTML comment is skipped."""
    decks_dir = tmp_path / "decks" / "Default"
    decks_dir.mkdir(parents=True)
    note_file = decks_dir / "1.md"
    note_file.write_text(
        "<!-- note: nid=1 notetype=Basic tags= deck=Default\n## Front\nHello\n",
        encoding="utf-8",
    )
    result = preview_import(tmp_path)
    assert result.notes_created == 0


def test_compute_git_checksums_malformed_note(tmp_path):
    """Malformed notes are excluded from git checksums."""
    decks_dir = tmp_path / "decks" / "Default"
    decks_dir.mkdir(parents=True)
    # Valid note
    (decks_dir / "1.md").write_text(
        '<!-- note: nid=1 notetype=Basic tags=tag1 deck=Default -->\n## Front\nHello\n',
        encoding="utf-8",
    )
    # Malformed note
    (decks_dir / "2.md").write_text(
        'garbage content no header\n',
        encoding="utf-8",
    )
    checksums, notes = compute_git_checksums(tmp_path)
    assert "1" in checksums
    assert "2" not in checksums
    assert 1 in notes
    assert 2 not in notes


def test_compute_git_checksums_empty_decks_dir(tmp_path):
    """Empty decks dir produces empty checksums."""
    (tmp_path / "decks").mkdir(parents=True)
    checksums, notes = compute_git_checksums(tmp_path)
    assert checksums == {}
    assert notes == {}


@pytest.mark.integration
def test_import_from_repo_malformed(tmp_path, anki_session):
    """import_from_repo gracefully handles malformed note files."""
    col = anki_session.collection

    # Set up a basic notetype in the collection
    nt = col.models.new("Basic")
    fm = col.models.new_field("Front")
    col.models.add_field(nt, fm)
    bm = col.models.new_field("Back")
    col.models.add_field(nt, bm)
    tmpl = col.models.new_template("Card 1")
    tmpl["qfmt"] = "{{Front}}"
    tmpl["afmt"] = "{{Back}}"
    col.models.add_template(nt, tmpl)
    col.models.add_dict(nt)

    # Set up repo with a valid notetype and a mix of valid/malformed notes
    repo = tmp_path / "repo"
    import json
    notetypes_root = repo / "notetypes"
    nt_dir = notetypes_root / "Basic"
    nt_dir.mkdir(parents=True)
    (nt_dir / "meta.json").write_text(json.dumps({"name": "Basic", "id": 1}), encoding="utf-8")
    (nt_dir / "fields.json").write_text(json.dumps([
        {"name": "Front", "ord": 0},
        {"name": "Back", "ord": 1},
    ]), encoding="utf-8")
    card_dir = nt_dir / "Card 1"
    card_dir.mkdir()
    (card_dir / "front.html").write_text("{{Front}}", encoding="utf-8")
    (card_dir / "back.html").write_text("{{Back}}", encoding="utf-8")
    decks_dir = repo / "decks" / "Default"
    decks_dir.mkdir(parents=True)

    # Valid note
    (decks_dir / "1.md").write_text(
        '<!-- note: nid=1 notetype=Basic tags=tag1 deck=Default -->\n## Front\nQ1\n## Back\nA1\n',
        encoding="utf-8",
    )
    # Malformed note (missing notetype)
    (decks_dir / "2.md").write_text(
        '<!-- note: nid=2 tags= deck=Default -->\n## Front\nQ2\n',
        encoding="utf-8",
    )
    # Malformed note (no header)
    (decks_dir / "3.md").write_text(
        '## Front\nQ3\n',
        encoding="utf-8",
    )
    # Valid note that has no corresponding notetype yet
    (decks_dir / "4.md").write_text(
        '<!-- note: nid=4 notetype=Basic tags= deck=Default -->\n## Front\nQ4\n## Back\nA4\n',
        encoding="utf-8",
    )

    from anki_git.engine.importer import import_from_repo
    result = import_from_repo(col, repo)

    # 2 valid notes (1 and 4) should have been imported
    assert result.notes_created == 2
    assert len(result.errors) == 0
    assert len(result.warnings) == 0  # notetype Basic is present


def test_import_result_no_error_attr():
    """Regression: on_import_done callbacks use result.errors, not result.error.

    ImportResult has .errors (plural, List[str]) — not .error (singular str).
    Using result.error on ImportResult raises AttributeError.
    """
    r = ImportResult()
    assert not hasattr(r, "error"), "ImportResult has .errors, not .error"
    assert isinstance(r.errors, list)
    assert r.errors == []


@pytest.mark.integration
def test_import_from_repo_with_error(tmp_path, anki_session):
    """Error during import populates .errors (not .error)."""
    col = anki_session.collection
    repo = tmp_path / "repo"
    (repo / "notetypes").mkdir(parents=True)
    (repo / "decks" / "Default").mkdir(parents=True)

    # Write a binary .md file that triggers UnicodeDecodeError during import
    (repo / "decks" / "Default" / "1.md").write_bytes(b"\xff\xfe\x00\x01")

    from anki_git.engine.importer import import_from_repo
    result = import_from_repo(col, repo)

    assert len(result.errors) > 0
    assert isinstance(result.errors, list)


@pytest.mark.integration
def test_import_partial_selection_no_reappearance(tmp_path, anki_session):
    """Partial import does not clobber checksums for unselected notes, and
    the verification commit stages only imported-note files — so unselected
    changes still appear in the next delta diff, and a full round-trip
    leaves the repo clean."""
    from anki_git.engine.checksums import load_meta
    from anki_git.engine.diff import compute_import_diff_delta
    from anki_git.engine.exporter import export_collection
    from anki_git.engine.importer import pull_from_repo

    col = anki_session.collection
    repo_path = tmp_path / "repo"

    # --- create 2 notes in Anki ---
    nt = col.models.by_name("Basic")
    assert nt is not None

    note1 = col.new_note(nt)
    note1.fields[0] = "Note1 Front"
    note1.fields[1] = "Note1 Back"
    col.add_note(note1, col.decks.id("Default"))
    nid1 = note1.id

    note2 = col.new_note(nt)
    note2.fields[0] = "Note2 Front"
    note2.fields[1] = "Note2 Back"
    col.add_note(note2, col.decks.id("Default"))
    nid2 = note2.id

    # --- export to repo (creates git repo + initial commit + meta) ---
    export_collection(col, repo_path)

    meta = load_meta(repo_path)
    assert len(meta.get("note_checksums", {})) == 2

    # --- modify both note files in the repo ---
    for nid in (nid1, nid2):
        f = repo_path / "decks" / "Default" / f"{nid}.md"
        content = f.read_text(encoding="utf-8")
        content = content.replace("Front", "Front Modified")
        f.write_text(content, encoding="utf-8")

    # --- delta diff detects both ---
    delta = compute_import_diff_delta(col, repo_path)
    assert delta.report.has_changes
    assert len(delta.report.note_diffs) == 2

    # --- simulate partial selection: only nid1 ---
    selected_nids = {nid1}
    filtered_anki = {k: v for k, v in delta.anki_checksums.items()
                     if int(k) in selected_nids}
    filtered_git = {k: v for k, v in delta.git_checksums.items()
                    if int(k) in selected_nids}
    filtered_repo_notes = {k: v for k, v in delta.repo_notes.items()
                           if k in selected_nids}

    result1 = pull_from_repo(
        col, repo_path,
        sync_mode="accept_all",
        anki_checksums=filtered_anki,
        git_checksums=filtered_git,
        git_notes_lookup=filtered_repo_notes,
        repo_notetypes=delta.repo_notetypes,
    )
    assert result1.notes_updated == 1
    assert len(result1.errors) == 0

    # --- nid2's checksum must still be in meta ---
    meta = load_meta(repo_path)
    checksums = meta.get("note_checksums", {})
    assert str(nid2) in checksums, "nid2 checksum was clobbered"

    # --- delta diff again: only nid2 should appear ---
    delta2 = compute_import_diff_delta(col, repo_path)
    assert delta2.report.has_changes, (
        "nid2 should still show as pending after partial import"
    )
    remaining = {nd.nid for nd in delta2.report.note_diffs}
    assert remaining == {nid2}, f"Expected only nid2 pending, got {remaining}"

    # --- import remaining note ---
    selected_nids2 = {nid2}
    filtered_anki2 = {k: v for k, v in delta2.anki_checksums.items()
                      if int(k) in selected_nids2}
    filtered_git2 = {k: v for k, v in delta2.git_checksums.items()
                     if int(k) in selected_nids2}
    filtered_repo_notes2 = {k: v for k, v in delta2.repo_notes.items()
                            if k in selected_nids2}

    result2 = pull_from_repo(
        col, repo_path,
        sync_mode="accept_all",
        anki_checksums=filtered_anki2,
        git_checksums=filtered_git2,
        git_notes_lookup=filtered_repo_notes2,
        repo_notetypes=delta2.repo_notetypes,
    )
    assert result2.notes_updated == 1
    assert len(result2.errors) == 0

    # --- final delta diff: nothing should show ---
    delta3 = compute_import_diff_delta(col, repo_path)
    assert not delta3.report.has_changes, (
        "All notes imported — nothing should remain pending"
    )

    # --- git status should be clean ---
    from anki_git.engine.git_ops import open_repo
    repo = open_repo(repo_path)
    assert repo is not None
    status = repo.git.status("--porcelain").strip()
    assert not status, f"Expected clean repo, got: {status}"
