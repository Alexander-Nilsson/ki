from __future__ import annotations

"""Three-way merge conflict detection.

Store {nid: md5(content)} in .ki/meta.json for every exported note.
Compare three states:
  - base: last exported state (checksums in meta.json)
  - local: current Anki collection
  - remote: Git repo state

Conflict cases:
  1. Changed in both (differently) -> conflict (ask user)
  2. Changed only in Anki -> Anki wins (push direction)
  3. Changed only in Git -> Git wins (pull direction)
  4. Deleted in Anki, same in Git -> delete from Git
  5. Deleted in Git, same in Anki -> delete from Anki (with confirmation)
  6. Deleted in both -> already gone
  7. Deleted in one, changed in other -> conflict
"""

from enum import Enum
from typing import Dict, List, Optional
from dataclasses import dataclass, field

from anki_git.config import SyncMode


class ConflictType(Enum):
    CONFLICT = "conflict"
    ANKI_WINS = "anki_wins"
    GIT_WINS = "git_wins"
    DELETE_FROM_GIT = "delete_from_git"
    DELETE_FROM_ANKI = "delete_from_anki"
    ALREADY_GONE = "already_gone"


@dataclass
class NoteConflict:
    nid: int
    conflict_type: ConflictType
    anki_content: Optional[str] = None
    git_content: Optional[str] = None
    base_content: Optional[str] = None
    resolved: bool = False
    resolution: Optional[str] = None


@dataclass
class ConflictReport:
    conflicts: List[NoteConflict] = field(default_factory=list)

    @property
    def has_conflicts(self) -> bool:
        return any(c.conflict_type == ConflictType.CONFLICT for c in self.conflicts)

    @property
    def total(self) -> int:
        return len(self.conflicts)


def resolve_conflicts(report: ConflictReport, sync_mode: str) -> None:
    """Auto-resolve conflicts based on sync_mode.

    Modifies the report in-place, marking conflicts as resolved.
    """
    for c in report.conflicts:
        if c.resolved:
            continue
        if c.conflict_type == ConflictType.CONFLICT:
            if sync_mode == SyncMode.PREFER_ANKI:
                c.resolution = "anki"
                c.resolved = True
            elif sync_mode == SyncMode.PREFER_REPO:
                c.resolution = "git"
                c.resolved = True
            elif sync_mode == SyncMode.ACCEPT_ALL:
                c.resolution = "anki"
                c.resolved = True
            # ALWAYS_ASK: leave unresolved
        elif c.conflict_type == ConflictType.ANKI_WINS:
            c.resolution = "anki"
            c.resolved = True
        elif c.conflict_type == ConflictType.GIT_WINS:
            c.resolution = "git"
            c.resolved = True
        elif c.conflict_type == ConflictType.DELETE_FROM_GIT:
            c.resolution = "anki"
            c.resolved = True
        elif c.conflict_type == ConflictType.DELETE_FROM_ANKI:
            c.resolution = "git"
            c.resolved = True
        elif c.conflict_type == ConflictType.ALREADY_GONE:
            c.resolved = True


@dataclass
class NotetypeComponentConflict:
    component_type: str  # "field", "template", "css"
    name: str
    anki_content: str = ""
    git_content: str = ""
    resolved: bool = False
    resolution: Optional[str] = None


def merge_notetypes(
    anki_nt,
    git_nt,
    sync_mode: str,
):
    """Two-way merge of notetypes using field/template IDs.

    Returns (merged_notetype, component_conflicts).
    The caller should check component_conflicts and handle unresolved ones.
    """
    conflicts: List[NotetypeComponentConflict] = []

    # ── Merge fields ──────────────────────────────────────────────
    def field_key(f):
        return f.id if f.id else hash((f.name, f.ord))

    anki_fields_by_key = {field_key(f): f for f in anki_nt.fields}
    git_fields_by_key = {field_key(f): f for f in git_nt.fields}
    all_field_keys = set(anki_fields_by_key) | set(git_fields_by_key)

    merged_fields = []
    for key in sorted(all_field_keys):
        af = anki_fields_by_key.get(key)
        gf = git_fields_by_key.get(key)
        if af and gf:
            if af != gf:
                c = NotetypeComponentConflict(
                    component_type="field", name=af.name,
                    anki_content=repr(af), git_content=repr(gf),
                )
                if sync_mode == SyncMode.PREFER_REPO:
                    c.resolved = True
                    c.resolution = "git"
                    merged_fields.append(gf)
                elif sync_mode in (SyncMode.PREFER_ANKI, SyncMode.ACCEPT_ALL):
                    c.resolved = True
                    c.resolution = "anki"
                    merged_fields.append(af)
                else:
                    # always_ask — leave unresolved, default to anki
                    merged_fields.append(af)
                conflicts.append(c)
            else:
                merged_fields.append(af)
        elif af:
            merged_fields.append(af)
        else:
            merged_fields.append(gf)

    # Re-number ords sequentially
    for i, f in enumerate(merged_fields):
        f.ord = i

    # ── Merge templates ───────────────────────────────────────────
    def tmpl_key(t):
        return t.id if t.id else hash((t.name, t.ord))

    anki_tmpls_by_key = {tmpl_key(t): t for t in anki_nt.templates}
    git_tmpls_by_key = {tmpl_key(t): t for t in git_nt.templates}
    all_tmpl_keys = set(anki_tmpls_by_key) | set(git_tmpls_by_key)

    merged_templates = []
    for key in sorted(all_tmpl_keys):
        at = anki_tmpls_by_key.get(key)
        gt = git_tmpls_by_key.get(key)
        if at and gt:
            if at != gt:
                c = NotetypeComponentConflict(
                    component_type="template", name=at.name,
                    anki_content=repr(at), git_content=repr(gt),
                )
                if sync_mode == SyncMode.PREFER_REPO:
                    c.resolved = True
                    c.resolution = "git"
                    merged_templates.append(gt)
                elif sync_mode in (SyncMode.PREFER_ANKI, SyncMode.ACCEPT_ALL):
                    c.resolved = True
                    c.resolution = "anki"
                    merged_templates.append(at)
                else:
                    merged_templates.append(at)
                conflicts.append(c)
            else:
                merged_templates.append(at)
        elif at:
            merged_templates.append(at)
        else:
            merged_templates.append(gt)

    for i, t in enumerate(merged_templates):
        t.ord = i

    # ── Merge CSS ─────────────────────────────────────────────────
    if anki_nt.css != git_nt.css:
        c = NotetypeComponentConflict(
            component_type="css", name="style.css",
            anki_content=anki_nt.css, git_content=git_nt.css,
        )
        if sync_mode == SyncMode.PREFER_REPO:
            c.resolved = True
            c.resolution = "git"
            css = git_nt.css
        elif sync_mode in (SyncMode.PREFER_ANKI, SyncMode.ACCEPT_ALL):
            c.resolved = True
            c.resolution = "anki"
            css = anki_nt.css
        else:
            css = anki_nt.css
        conflicts.append(c)
    else:
        css = anki_nt.css

    merged = anki_nt.__class__(
        name=anki_nt.name,
        id=anki_nt.id,
        fields=merged_fields,
        templates=merged_templates,
        css=css,
        sort_field=anki_nt.sort_field,
        type=anki_nt.type,
        deck_presets=anki_nt.deck_presets,
    )
    return merged, conflicts


def detect_conflicts(
    base_checksums: Dict[str, str],
    anki_checksums: Dict[str, str],
    git_checksums: Dict[str, str],
) -> ConflictReport:
    report = ConflictReport()
    all_nids = set(base_checksums) | set(anki_checksums) | set(git_checksums)

    for nid_str in all_nids:
        nid = int(nid_str)
        base = base_checksums.get(nid_str)
        anki = anki_checksums.get(nid_str)
        git = git_checksums.get(nid_str)

        if anki is None and git is None:
            report.conflicts.append(NoteConflict(nid=nid, conflict_type=ConflictType.ALREADY_GONE))
        elif anki is None:
            if git == base:
                report.conflicts.append(NoteConflict(nid=nid, conflict_type=ConflictType.DELETE_FROM_GIT))
            else:
                report.conflicts.append(NoteConflict(nid=nid, conflict_type=ConflictType.CONFLICT))
        elif git is None:
            if anki == base:
                report.conflicts.append(NoteConflict(nid=nid, conflict_type=ConflictType.DELETE_FROM_ANKI))
            else:
                report.conflicts.append(NoteConflict(nid=nid, conflict_type=ConflictType.CONFLICT))
        elif anki == git:
            pass
        elif anki == base and git != base:
            report.conflicts.append(NoteConflict(nid=nid, conflict_type=ConflictType.GIT_WINS))
        elif git == base and anki != base:
            report.conflicts.append(NoteConflict(nid=nid, conflict_type=ConflictType.ANKI_WINS))
        else:
            report.conflicts.append(NoteConflict(nid=nid, conflict_type=ConflictType.CONFLICT))

    return report
