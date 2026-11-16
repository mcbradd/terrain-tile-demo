"""Command `licenses` (SPEC 4.2): third-party license table of docs/PROVENANCE.md from installed metadata. No network."""
import json
import re
import tomllib
from importlib import metadata
from pathlib import Path

HEADING = "## Third-party packages"


def _py_license(name: str) -> tuple[str, str]:
    m = metadata.metadata(name)
    lic = m.get("License-Expression") or ""
    if not lic:
        raw = (m.get("License") or "").strip()
        lic = raw if raw and len(raw) < 80 and "\n" not in raw else ""
    if not lic:
        lic = "; ".join(c.split("::")[-1].strip() for c in m.get_all("Classifier") or [] if c.startswith("License ::"))
    return metadata.version(name), lic or "UNKNOWN"


def rows(root: Path) -> list[tuple[str, str, str, str]]:
    proj = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    deps = proj["project"]["dependencies"] + [d for g in proj.get("dependency-groups", {}).values() for d in g]
    out = []
    for d in (d for d in deps if not d.startswith("tilepipe")):   # our own launcher is not third-party
        name = re.split(r"[=<>!~\[ ]", d, maxsplit=1)[0]
        out.append((name, *_py_license(name), "python"))
    pkg = json.loads((root / "package.json").read_text(encoding="utf-8"))
    for name in pkg.get("dependencies", {}):
        meta = json.loads((root / "node_modules" / name / "package.json").read_text(encoding="utf-8"))
        out.append((name, meta["version"], str(meta.get("license", "UNKNOWN")), "npm"))
    return sorted(out, key=lambda r: (r[3], r[0].lower()))


def run(root: Path) -> None:
    root = Path(root)
    data = rows(root)
    table = [HEADING, "", "License strings read from installed package metadata by `tilepipe licenses`.", "",
             "| Package | Version | License | Source |", "| --- | --- | --- | --- |"]
    table += [f"| {n} | {v} | {lic} | {src} |" for n, v, lic, src in data]
    block = "\n".join(table) + "\n"
    f = root / "docs" / "PROVENANCE.md"
    old = f.read_text(encoding="utf-8") if f.exists() else ""
    m = re.search(rf"^{re.escape(HEADING)}\n.*?(?=^## |\Z)", old, re.S | re.M)
    if m:
        new = old[:m.start()] + block + ("\n" if m.end() < len(old) else "") + old[m.end():]
    else:
        new = (old.rstrip("\n") + "\n\n" if old else "") + block
    f.parent.mkdir(exist_ok=True)
    f.write_text(new, encoding="utf-8", newline="\n")
    print(f"licenses: {len(data)} packages -> docs/PROVENANCE.md")
