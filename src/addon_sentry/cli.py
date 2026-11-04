"""Command line interface."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import __version__, engine, rules

LEVEL = {s: i for i, s in enumerate(rules.SEVERITIES)}
LABEL = {
    "es": {
        "caps": "Qué puede hacer",
        "findings": "Señales",
        "none": "Nada que reportar.",
        "files": "archivos",
        "lines": "líneas de Lua",
        "auras": "auras",
        "pieces": "bloques de código",
    },
    "en": {
        "caps": "What it can do",
        "findings": "Signals",
        "none": "Nothing to report.",
        "files": "files",
        "lines": "lines of Lua",
        "auras": "auras",
        "pieces": "pieces of code",
    },
}
COLORS = {"critical": "41;97;1", "high": "31;1", "medium": "33;1", "low": "36", "info": "2", "bold": "1", "dim": "2"}


def text_report(d: dict, lang: str, color: bool, verbose: bool) -> str:
    def c(s: str, what: str) -> str:
        return f"\033[{COLORS[what]}m{s}\033[0m" if color else s

    L = LABEL[lang]
    out = [c(f"addon-sentry {d['tool']['version']}", "bold") + c(f" · {d['target']}", "dim")]
    for a in d["addons"]:
        bits = [a.get("title") or a["file"], a.get("version"), a.get("author")]
        out.append(c("  " + " · ".join(b for b in bits if b), "dim"))
    st = d["stats"]
    if "auras" in st:
        out.append(c(f"  {st['auras']} {L['auras']}, {st['code_pieces']} {L['pieces']}, {st['lines']} {L['lines']}", "dim"))
    else:
        out.append(c(f"  {st['files']} {L['files']}, {st['lines']} {L['lines']}", "dim"))
    out.append("")
    v = d["verdict"]
    out.append(c(f" {v['text'].upper()} ", v["level"] if v["level"] != "info" else "low"))
    out.append("")
    if d["capabilities"]:
        out.append(c(L["caps"], "bold"))
        for cap in d["capabilities"]:
            ex = cap["evidence"][0]
            out.append(f"  • {cap['text']}" + c(f"  ({ex['detail']}, {ex['file']}:{ex['line']})", "dim"))
        out.append("")
    shown = [f for f in d["findings"] if verbose or f["severity"] != "info"]
    out.append(c(L["findings"], "bold"))
    if not shown:
        out.append("  " + L["none"])
    for f in shown:
        out.append(f"  {c(f['severity_text'].upper(), f['severity'])} {f['title']}")
        out.append(c(f"    {f['explanation']}", "dim"))
        for e in f["evidence"][: (10 if verbose else 3)]:
            where = f"{e['file']}:{e['line']}" if e["line"] else e["file"]
            snippet = f"  {e['snippet']}" if e.get("snippet") else ""
            out.append(f"    {where}  {e['detail']}" + c(snippet, "dim"))
        if f["count"] > (10 if verbose else 3):
            out.append(c(f"    … +{f['count'] - (10 if verbose else 3)}", "dim"))
    out.append("")
    out.append(c(d["disclaimer"], "dim"))
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="addon-sentry", description="Checks a World of Warcraft addon (zip or folder) for warning signs before you install it."
    )
    p.add_argument("path", type=Path, nargs="?", help="addon .zip or folder")
    p.add_argument(
        "--aura",
        metavar="FILE",
        help="a WeakAuras import string (!WA:2!...) in a text file, or - to read it from standard input",
    )
    p.add_argument("--lang", choices=["es", "en"], default=os.environ.get("ADDON_SENTRY_LANG", "es"))
    p.add_argument("-f", "--format", choices=["text", "json"], default="text")
    p.add_argument("-v", "--verbose", action="store_true", help="show every piece of evidence and the info-level signals")
    p.add_argument(
        "--fail-on",
        choices=["low", "medium", "high", "critical", "never"],
        default="high",
        help="exit 1 at this verdict or worse (default: high)",
    )
    p.add_argument("--no-color", action="store_true")
    p.add_argument("--version", action="version", version=f"addon-sentry {__version__}")
    args = p.parse_args(argv)
    if (args.path is None) == (args.aura is None):
        p.error("give an addon (zip or folder) or --aura FILE")
    if args.path is not None and not args.path.exists():
        p.error(f"{args.path} does not exist")
    try:
        if args.aura is not None:
            if args.aura == "-":
                text = sys.stdin.read()
            else:
                aura = Path(args.aura)
                if not aura.is_file():
                    p.error(f"{aura} does not exist")
                text = aura.read_text(encoding="utf-8", errors="replace")
            report = engine.scan_aura(text)
        else:
            report = engine.scan_path(args.path)
    except engine.ScanError as e:
        print(f"addon-sentry: {e}", file=sys.stderr)
        return 2
    d = report.to_dict(args.lang)
    if args.format == "json":
        sys.stdout.write(json.dumps(d, indent=2, ensure_ascii=False) + "\n")
    else:
        color = not args.no_color and sys.stdout.isatty() and "NO_COLOR" not in os.environ
        sys.stdout.write(text_report(d, args.lang, color, args.verbose))
    if args.fail_on != "never" and LEVEL[report.severity] >= LEVEL[args.fail_on]:
        return 1
    return 0
