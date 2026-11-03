"""Writes web/rules.json from src/addon_sentry/rules.py (the JavaScript engine reads it)."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from addon_sentry import rules  # noqa: E402

out = Path(__file__).resolve().parents[1] / "web" / "rules.json"
out.write_text(json.dumps(rules.export(), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
print(f"wrote {out}")
