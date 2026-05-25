from pathlib import Path
from typing import Dict, List, Optional


def _safe(name: str) -> str:
    return "".join(c if c.isalnum() or c in " _-." else "_" for c in name).strip()


def notetype_dir_path(notetypes_root: Path, name: str) -> Path:
    return notetypes_root / _safe(name)


def notetype_paths(notetypes_root: Path, name: str) -> List[Path]:
    nt_dir = notetype_dir_path(notetypes_root, name)
    if not nt_dir.is_dir():
        return []
    paths = []
    for entry in sorted(nt_dir.rglob("*")):
        if entry.is_file():
            paths.append(entry)
    return paths


class NotetypeField:
    def __init__(self, name: str, ord: int, font: str = "Arial", size: int = 20, sticky: bool = False, rtl: bool = False, nt_id: int = 0):
        self.name = name
        self.ord = ord
        self.font = font
        self.size = size
        self.sticky = sticky
        self.rtl = rtl
        self.id = nt_id

    def __eq__(self, other):
        if not isinstance(other, NotetypeField):
            return NotImplemented
        return (self.name == other.name and self.ord == other.ord
                and self.font == other.font and self.size == other.size
                and self.sticky == other.sticky and self.rtl == other.rtl)

    def __hash__(self):
        return hash((self.name, self.ord))


class NotetypeTemplate:
    def __init__(self, name: str, ord: int, qfmt: str, afmt: str, bqfmt: str = "", bafmt: str = "", nt_id: int = 0):
        self.name = name
        self.ord = ord
        self.qfmt = qfmt.replace("\r\n", "\n")
        self.afmt = afmt.replace("\r\n", "\n")
        self.bqfmt = bqfmt.replace("\r\n", "\n")
        self.bafmt = bafmt.replace("\r\n", "\n")
        self.id = nt_id

    def __eq__(self, other):
        if not isinstance(other, NotetypeTemplate):
            return NotImplemented
        return (self.name == other.name and self.ord == other.ord
                and self.qfmt == other.qfmt and self.afmt == other.afmt
                and self.bqfmt == other.bqfmt and self.bafmt == other.bafmt)

    def __hash__(self):
        return hash((self.name, self.ord))


class Notetype:
    def __init__(
        self,
        name: str,
        id: int,
        fields: List[NotetypeField],
        templates: List[NotetypeTemplate],
        css: str,
        sort_field: int = 0,
        type: int = 0,
        deck_presets: Optional[dict] = None,
    ):
        self.name = name
        self.id = id
        self.fields = fields
        self.templates = templates
        self.css = css.replace("\r\n", "\n")
        self.sort_field = sort_field
        self.type = type
        self.deck_presets = deck_presets or {}

    def __eq__(self, other):
        if not isinstance(other, Notetype):
            return NotImplemented
        return (self.name == other.name and self.fields == other.fields
                and self.templates == other.templates and self.css == other.css)

    @classmethod
    def from_anki_dict(cls, d: dict) -> "Notetype":
        fields = [
            NotetypeField(
                name=f["name"],
                ord=f["ord"],
                font=f.get("font", "Arial"),
                size=f.get("size", 20),
                sticky=f.get("sticky", False),
                rtl=f.get("rtl", False),
                nt_id=f.get("id", 0),
            )
            for f in d.get("flds", [])
        ]
        templates = [
            NotetypeTemplate(
                name=t["name"],
                ord=t["ord"],
                qfmt=t.get("qfmt", ""),
                afmt=t.get("afmt", ""),
                bqfmt=t.get("bqfmt", ""),
                bafmt=t.get("bafmt", ""),
                nt_id=t.get("id", 0),
            )
            for t in d.get("tmpls", [])
        ]
        return cls(
            name=d["name"],
            id=d["id"],
            fields=fields,
            templates=templates,
            css=d.get("css", ""),
            sort_field=d.get("sortf", 0),
            type=d.get("type", 0),
            deck_presets=d.get("deck_presets", {}),
        )


def write_notetype(notetypes_root: Path, nt: Notetype) -> None:
    nt_dir = notetype_dir_path(notetypes_root, nt.name)
    nt_dir.mkdir(parents=True, exist_ok=True)

    import json

    (nt_dir / "meta.json").write_text(
        json.dumps({
            "name": nt.name,
            "id": nt.id,
            "sort_field": nt.sort_field,
            "type": nt.type,
            "deck_presets": nt.deck_presets,
        }, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    fields_data = []
    for f in nt.fields:
        fd = {"name": f.name, "ord": f.ord}
        if f.font != "Arial":
            fd["font"] = f.font
        if f.size != 20:
            fd["size"] = f.size
        if f.sticky:
            fd["sticky"] = True
        if f.rtl:
            fd["rtl"] = True
        if f.id:
            fd["id"] = f.id
        fields_data.append(fd)
    (nt_dir / "fields.json").write_text(
        json.dumps(fields_data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    templates_data = []
    for t in nt.templates:
        td = {"name": t.name, "ord": t.ord}
        if t.id:
            td["id"] = t.id
        templates_data.append(td)
    (nt_dir / "templates.json").write_text(
        json.dumps(templates_data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    if nt.css:
        (nt_dir / "style.css").write_text(nt.css, encoding="utf-8")
    elif (nt_dir / "style.css").exists():
        (nt_dir / "style.css").unlink()

    existing_card_dirs = set(
        d.name for d in nt_dir.iterdir() if d.is_dir()
    )
    written_card_names = set()
    for t in nt.templates:
        card_dir = nt_dir / _safe(t.name)
        card_dir.mkdir(parents=True, exist_ok=True)
        written_card_names.add(card_dir.name)
        (card_dir / "front.html").write_text(t.qfmt, encoding="utf-8")
        (card_dir / "back.html").write_text(t.afmt, encoding="utf-8")
    for dname in existing_card_dirs - written_card_names:
        import shutil
        shutil.rmtree(str(nt_dir / dname))


def read_notetype(nt_dir: Path) -> Optional[Notetype]:
    if not nt_dir.is_dir():
        return None

    import json

    meta_path = nt_dir / "meta.json"
    fields_path = nt_dir / "fields.json"
    if not meta_path.exists() or not fields_path.exists():
        return None

    meta = json.loads(meta_path.read_text(encoding="utf-8"))

    fields_data = json.loads(fields_path.read_text(encoding="utf-8"))
    fields = []
    for i, fd in enumerate(fields_data):
        fields.append(NotetypeField(
            name=fd["name"],
            ord=fd.get("ord", i),
            font=fd.get("font", "Arial"),
            size=fd.get("size", 20),
            sticky=fd.get("sticky", False),
            rtl=fd.get("rtl", False),
            nt_id=fd.get("id", 0),
        ))

    css = ""
    css_path = nt_dir / "style.css"
    if css_path.exists():
        css = css_path.read_text(encoding="utf-8")

    templates_path = nt_dir / "templates.json"
    templates = []
    if templates_path.exists():
        templates_data = json.loads(templates_path.read_text(encoding="utf-8"))
        for td in templates_data:
            card_dir = nt_dir / _safe(td["name"])
            front_path = card_dir / "front.html"
            back_path = card_dir / "back.html"
            if not front_path.exists() or not back_path.exists():
                continue
            templates.append(NotetypeTemplate(
                name=td["name"],
                ord=td.get("ord", len(templates)),
                qfmt=front_path.read_text(encoding="utf-8"),
                afmt=back_path.read_text(encoding="utf-8"),
                nt_id=td.get("id", 0),
            ))
    else:
        card_dirs = sorted(d for d in nt_dir.iterdir() if d.is_dir())
        for i, cdir in enumerate(card_dirs):
            front_path = cdir / "front.html"
            back_path = cdir / "back.html"
            if not front_path.exists() or not back_path.exists():
                continue
            templates.append(NotetypeTemplate(
                name=cdir.name,
                ord=i,
                qfmt=front_path.read_text(encoding="utf-8"),
                afmt=back_path.read_text(encoding="utf-8"),
            ))

    return Notetype(
        name=meta.get("name", nt_dir.name),
        id=meta.get("id", 0),
        fields=fields,
        templates=templates,
        css=css,
        sort_field=meta.get("sort_field", 0),
        type=meta.get("type", 0),
        deck_presets=meta.get("deck_presets", {}),
    )


def read_all_notetypes(notetypes_root: Path) -> Dict[str, Notetype]:
    result = {}
    if not notetypes_root.exists():
        return result
    for entry in sorted(notetypes_root.iterdir()):
        if entry.is_dir() and (entry / "meta.json").exists() and (entry / "fields.json").exists():
            try:
                nt = read_notetype(entry)
                if nt:
                    result[nt.name] = nt
            except Exception:
                continue
    return result
