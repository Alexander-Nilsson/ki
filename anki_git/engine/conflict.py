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
