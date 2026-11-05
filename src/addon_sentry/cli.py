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


FOREVER_COLOR = {"loads": "low", "outdated": "medium", "no_toc": "medium", "excluded": "dim", "unknown": "dim", "none": "medium"}


def text_report(d: dict, lang: str, color: bool, verbose: bool) -> str:
    def c(s: str, what: str) -> str:
        return f"\033[{COLORS[what]}m{s}\033[0m" if color else s

    if d.get("multi"):
        return _multi_text(d, lang, color, verbose, c)
    return _single_text(d, lang, color, verbose, c, header=True)


def _multi_text(d: dict, lang: str, color: bool, verbose: bool, c) -> str:
    A = rules.AUDIT[lang]
    out = [
        c(f"addon-sentry {d['tool']['version']}", "bold") + c(f" · {d['target']} · " + A["count"].format(n=d["stats"]["addons"]), "dim"),
        "",
    ]
    v = d["verdict"]
    out.append(c(f" {v['text'].upper()} ", v["level"] if v["level"] != "info" else "low") + c(f"  {A['worst']}", "dim"))
    out.append("")
    rows = [
        (
            s["title"] if s["title"] != s["name"] else s["name"],
            s["version"] if "@" not in s["version"] else "",
            s["verdict"]["text"],
            s["forever"]["text"],
            ", ".join(x["text"] for x in s["capabilities"]) or A["none"],
            s,
        )
        for s in d["summary"]
    ]
    widths = [
        max(len(str(r[i])) for r in rows + [(A["addon"], A["version"], A["verdict"], A["forever"], A["caps"], None)]) for i in range(5)
    ]
    widths = [min(w, 32) for w in widths]

    def cell(s: str, i: int) -> str:
        s = s if len(s) <= widths[i] else s[: widths[i] - 1] + "…"
        return s.ljust(widths[i])

    out.append(
        c("  " + "  ".join(cell(h, i) for i, h in enumerate((A["addon"], A["version"], A["verdict"], A["forever"], A["caps"]))), "bold")
    )
    for name, ver, verdict, forever, caps, s in rows:
        lvl = s["verdict"]["level"]
        out.append(
            "  "
            + cell(name, 0)
            + "  "
            + c(cell(ver, 1), "dim")
            + "  "
            + c(cell(verdict, 2), lvl if lvl != "info" else "low")
            + "  "
            + c(cell(forever, 3), FOREVER_COLOR[s["forever"]["status"]])
            + "  "
            + c(cell(caps, 4), "dim")
        )
    out.append("")
    for r in d["reports"]:
        out.append(c("─" * 60, "dim"))
        out.append(_single_text(r, lang, color, verbose, c, header=False).rstrip("\n"))
        out.append("")
    out.append(c(d["disclaimer"], "dim"))
    return "\n".join(out) + "\n"


def _single_text(d: dict, lang: str, color: bool, verbose: bool, c, header: bool) -> str:
    L = LABEL[lang]
    out = [c(f"addon-sentry {d['tool']['version']}", "bold") + c(f" · {d['target']}", "dim") if header else c(d["target"], "bold")]
    for a in d["addons"]:
        bits = [a.get("title") or a["file"], a.get("version"), a.get("author")]
        out.append(c("  " + " · ".join(b for b in bits if b), "dim"))
    st = d["stats"]
    if "auras" in st:
        auras = f"{st['auras']} {L['auras'] if st['auras'] != 1 else 'aura'}"
        out.append(c(f"  {auras}, {st['code_pieces']} {L['pieces']}, {st['lines']} {L['lines']}", "dim"))
    else:
        out.append(c(f"  {st['files']} {L['files']}, {st['lines']} {L['lines']}", "dim"))
    out.append("")
    v = d["verdict"]
    out.append(c(f" {v['text'].upper()} ", v["level"] if v["level"] != "info" else "low"))
    f = d.get("forever")
    if f:
        out.append(c(f"  {f['text']}", FOREVER_COLOR[f["status"]]) + c(f"  {f['detail']}", "dim"))
    out.append("")
    if d["capabilities"]:
        out.append(c(L["caps"], "bold"))
        for cap in d["capabilities"]:
            ex = cap["evidence"][0]
            where = f"{ex['file']}:{ex['line']}" if ex["line"] else ex["file"]
            out.append(f"  • {cap['text']}" + c(f"  ({ex['detail']}, {where})", "dim"))
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
    if header:
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
