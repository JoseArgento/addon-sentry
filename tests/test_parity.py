"""The browser engine (web/sentry.js) must give exactly the same report as the Python one."""

import io
import json
import os
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

from addon_sentry import engine, rules

ROOT = Path(__file__).resolve().parents[1]
FIX = Path(__file__).parent / "fixtures"
REAL = Path(os.environ.get("ADDON_SENTRY_REAL_ADDONS", "/nonexistent"))

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")


def zip_folder(folder: Path, dest: Path) -> Path:
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(folder.rglob("*")):
            rel = p.relative_to(folder.parent)
            if any(part.startswith(".") for part in rel.parts):
                continue
            if p.is_file():
                z.write(p, rel.as_posix())
    return dest


def extra_zips(tmp: Path) -> list[Path]:
    """Hand-made zips that exercise the zip reader: stored entries, odd names, traversal, encrypted."""
    out = []
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(zipfile.ZipInfo("Odd/Odd.toc"), "## Interface: 16001\n## Title: |cff00ff00Odd|r\nmain.lua\n")
        z.writestr(zipfile.ZipInfo("Odd/main.lua"), "-- stored, not deflated\nlocal x = _G['Send'..'Mail']\nRunScript(x)\n")
        info = zipfile.ZipInfo("Odd/Ünïcode ñame.lua")
        info.flag_bits |= 0x800
        z.writestr(info, "GuildDisband()")
        z.writestr(zipfile.ZipInfo("../escape.lua"), "x")
        z.writestr(zipfile.ZipInfo("Odd/tool.EXE"), "MZ")
    p = tmp / "odd.zip"
    p.write_bytes(buf.getvalue())
    out.append(p)
    return out


def python_reports(path: Path) -> dict:
    try:
        r = engine.scan_bytes(path.read_bytes(), path.name)
    except engine.ScanError as e:
        return {"error": str(e)}
    return {"es": r.to_dict("es"), "en": r.to_dict("en")}


def test_rules_json_is_current():
    current = json.loads((ROOT / "web" / "rules.json").read_text(encoding="utf-8"))
    assert current == json.loads(json.dumps(rules.export())), "run tools/export_rules.py"


def test_engines_agree(tmp_path):
    zips = [zip_folder(d, tmp_path / f"{d.name}.zip") for d in sorted(FIX.iterdir()) if d.is_dir()]
    if REAL.is_dir():
        zips += [zip_folder(d, tmp_path / f"real-{d.name}.zip") for d in sorted(REAL.iterdir()) if d.is_dir()]
    zips += extra_zips(tmp_path)
    proc = subprocess.run(
        ["node", str(ROOT / "tests" / "parity_runner.js"), *map(str, zips)], capture_output=True, text=True, timeout=600, check=True
    )
    js = json.loads(proc.stdout)
    mismatches = []
    for z in zips:
        py = json.loads(json.dumps(python_reports(z), ensure_ascii=False))
        if py != js[str(z)]:
            mismatches.append(z.name)
            (tmp_path / f"{z.name}.py.json").write_text(json.dumps(py, indent=1, ensure_ascii=False))
            (tmp_path / f"{z.name}.js.json").write_text(json.dumps(js[str(z)], indent=1, ensure_ascii=False))
    assert not mismatches, f"engines disagree on {mismatches}; diffs in {tmp_path}"
