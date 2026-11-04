"""Builds dist/index.html: the page with the engine, the rules and the examples inlined (one self-contained file)."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from addon_sentry import rules  # noqa: E402

FIX = ROOT / "tests" / "fixtures"
EXAMPLES = [
    ("AuctionScam", {"es": "Estafa de subasta", "en": "Auction scam"}),
    ("Backdoor", {"es": "Puerta trasera", "en": "Backdoor"}),
    ("Packed", {"es": "Código escondido", "en": "Hidden code"}),
    ("Clean", {"es": "Addon limpio", "en": "Clean addon"}),
]
AURA_EXAMPLES = [
    ("mail_scam", {"es": "Aura que manda tu oro", "en": "Aura that mails your gold"}),
]


def examples() -> list[dict]:
    out = []
    for folder, label in EXAMPLES:
        files = {
            f"{folder}/{p.relative_to(FIX / folder).as_posix()}": p.read_text(encoding="utf-8")
            for p in sorted((FIX / folder).rglob("*"))
            if p.is_file()
        }
        out.append({"id": folder.lower(), "name": f"{folder}.zip", "label": label, "files": files})
    for name, label in AURA_EXAMPLES:
        text = (FIX / "auras" / f"{name}.txt").read_text(encoding="utf-8").strip()
        out.append({"id": "aura-" + name.replace("_", "-"), "label": label, "aura": text})
    return out


def js_literal(value) -> str:
    # Safe inside <script>: no "</" sequences.
    return json.dumps(value, ensure_ascii=False).replace("</", "<\\/")


def main() -> None:
    page = (ROOT / "web" / "page.html").read_text(encoding="utf-8")
    engine = (ROOT / "web" / "sentry.js").read_text(encoding="utf-8").replace("</script", "<\\/script")
    page = page.replace("/*__RULES__*/", "var ADDON_SENTRY_RULES = " + js_literal(rules.export()) + ";")
    page = page.replace("/*__ENGINE__*/", engine)
    page = page.replace("/*__EXAMPLES__*/", "var ADDON_SENTRY_EXAMPLES = " + js_literal(examples()) + ";")
    out = ROOT / "dist" / "index.html"
    out.parent.mkdir(exist_ok=True)
    out.write_text(page, encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
