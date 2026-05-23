"""Three-way merge conflict detection.

Store {nid: md5(content)} in .ki/meta.json for every exported note.
Compare three states:
  - base: last exported state (checksums in meta.json)
  - local: current Anki collection
  - remote: Git repo state

Conflict cases:
  1. Changed in Anki AND changed in Git → conflict (ask user)
  2. Changed only in Anki → Anki wins (push direction)
  3. Changed only in Git → Git wins (pull direction)
  4. Deleted in Anki, unchanged in Git → delete from Git
  5. Deleted in Git, unchanged in Anki → delete from Anki (with confirmation)
  6. Deleted in both → already gone
"""

from enum import Enum
from typing import Dict, List, Optional
from dataclasses import dataclass, field


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

        anki_changed = base is not None and anki is not None and base != anki
        git_changed = base is not None and git is not None and base != git

        if anki is None and git is None:
            report.conflicts.append(NoteConflict(nid=nid, conflict_type=ConflictType.ALREADY_GONE))
        elif anki is None:
            if git_changed:
                report.conflicts.append(NoteConflict(nid=nid, conflict_type=ConflictType.DELETE_FROM_ANKI))
            else:
                report.conflicts.append(NoteConflict(nid=nid, conflict_type=ConflictType.ALREADY_GONE))
        elif git is None:
            if anki_changed:
                report.conflicts.append(NoteConflict(nid=nid, conflict_type=ConflictType.DELETE_FROM_GIT))
            else:
                report.conflicts.append(NoteConflict(nid=nid, conflict_type=ConflictType.ALREADY_GONE))
        elif anki_changed and git_changed:
            report.conflicts.append(NoteConflict(nid=nid, conflict_type=ConflictType.CONFLICT))
        elif anki_changed:
            report.conflicts.append(NoteConflict(nid=nid, conflict_type=ConflictType.ANKI_WINS))
        elif git_changed:
            report.conflicts.append(NoteConflict(nid=nid, conflict_type=ConflictType.GIT_WINS))

    return report
