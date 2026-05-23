from pathlib import Path
from typing import List, Optional


CSS_FILENAME_SUFFIX = ".css"
YAML_FILENAME_SUFFIX = ".yaml"


class NotetypeField:
    def __init__(self, name: str, ord: int, font: str = "Arial", size: int = 20, sticky: bool = False):
        self.name = name
        self.ord = ord
        self.font = font
        self.size = size
        self.sticky = sticky


class NotetypeTemplate:
    def __init__(self, name: str, ord: int, qfmt: str, afmt: str, bqfmt: str = "", bafmt: str = ""):
        self.name = name
        self.ord = ord
        self.qfmt = qfmt
        self.afmt = afmt
        self.bqfmt = bqfmt
        self.bafmt = bafmt


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
        deck_presets: dict = None,
    ):
        self.name = name
        self.id = id
        self.fields = fields
        self.templates = templates
        self.css = css
        self.sort_field = sort_field
        self.type = type
        self.deck_presets = deck_presets or {}

    @classmethod
    def from_anki_dict(cls, d: dict) -> "Notetype":
        fields = [
            NotetypeField(
                name=f["name"],
                ord=f["ord"],
                font=f.get("font", "Arial"),
                size=f.get("size", 20),
                sticky=f.get("sticky", False),
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

    def to_yaml_lines(self) -> List[str]:
        lines = [f"name: {self.name}", f"id: {self.id}", "fields:"]
        for f in self.fields:
            lines.append(f"  - name: {f.name}")
            lines.append(f"    ord: {f.ord}")
            lines.append(f"    font: {f.font}")
            lines.append(f"    size: {f.size}")
            lines.append(f"    sticky: {str(f.sticky).lower()}")
        lines.append("templates:")
        for t in self.templates:
            lines.append(f"  - name: {t.name}")
            lines.append(f"    ord: {t.ord}")
            lines.append(f"    qfmt: {repr(t.qfmt)}")
            lines.append(f"    afmt: {repr(t.afmt)}")
            if t.bqfmt:
                lines.append(f"    bqfmt: {repr(t.bqfmt)}")
            if t.bafmt:
                lines.append(f"    bafmt: {repr(t.bafmt)}")
        lines.append(f"css: |")
        for css_line in self.css.split("\n"):
            lines.append(f"  {css_line}")
        lines.append(f"sort_field: {self.sort_field}")
        lines.append(f"type: {self.type}")
        return lines

    @classmethod
    def from_yaml_lines(cls, lines: List[str]) -> "Notetype":
        import yaml
        text = "\n".join(lines)
        d = yaml.safe_load(text)
        fields = [
            NotetypeField(name=f["name"], ord=f.get("ord", i), font=f.get("font", "Arial"), size=f.get("size", 20), sticky=f.get("sticky", False))
            for i, f in enumerate(d.get("fields", []))
        ]
        templates = [
            NotetypeTemplate(name=t["name"], ord=t.get("ord", i), qfmt=t.get("qfmt", ""), afmt=t.get("afmt", ""))
            for i, t in enumerate(d.get("templates", []))
        ]
        css = d.get("css", "").rstrip("\n")
        return cls(
            name=d["name"],
            id=d.get("id", 0),
            fields=fields,
            templates=templates,
            css=css,
            sort_field=d.get("sort_field", 0),
            type=d.get("type", 0),
        )


def notetype_paths(notetypes_dir: Path, name: str) -> tuple:
    safe_name = name.replace(" ", "_").replace("::", "__")
    yaml_path = notetypes_dir / f"{safe_name}{YAML_FILENAME_SUFFIX}"
    css_path = notetypes_dir / f"{safe_name}{CSS_FILENAME_SUFFIX}"
    return yaml_path, css_path


def write_notetype(notetypes_dir: Path, nt: Notetype) -> None:
    notetypes_dir.mkdir(parents=True, exist_ok=True)
    yaml_path, css_path = notetype_paths(notetypes_dir, nt.name)
    yaml_content = "\n".join(nt.to_yaml_lines())
    yaml_path.write_text(yaml_content, encoding="utf-8")
    if nt.css:
        css_path.write_text(nt.css, encoding="utf-8")
    elif css_path.exists():
        css_path.unlink()


def read_notetype(yaml_path: Path) -> Optional[Notetype]:
    if not yaml_path.exists():
        return None
    lines = yaml_path.read_text(encoding="utf-8").split("\n")
    css_path = yaml_path.with_suffix(CSS_FILENAME_SUFFIX)
    nt = Notetype.from_yaml_lines(lines)
    if css_path.exists():
        nt.css = css_path.read_text(encoding="utf-8")
    return nt


def read_all_notetypes(notetypes_dir: Path) -> dict:
    result = {}
    if not notetypes_dir.exists():
        return result
    for yaml_file in sorted(notetypes_dir.glob(f"*{YAML_FILENAME_SUFFIX}")):
        nt = read_notetype(yaml_file)
        if nt:
            result[nt.name] = nt
    return result
