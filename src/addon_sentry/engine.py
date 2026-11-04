"""Scans an addon (zip or folder) and builds a report.

Nothing is executed and nothing is written to disk: zip members are read in
memory with size limits, so the same code runs in the browser (Pyodide).
"""

from __future__ import annotations

import io
import math
import posixpath
import re
import stat
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from . import __version__, auras, rules
from .lexer import NAME, NUMBER, OP, STRING, Token
from .lua import FileScan, scan

MAX_ENTRIES = 20_000
MAX_TOTAL_BYTES = 300 * 1024 * 1024
MAX_FILE_BYTES = 40 * 1024 * 1024
MAX_RATIO = 200  # uncompressed/compressed, for big members (zip bombs)

CODE_RUNNERS = {"loadstring", "load", "RunScript"}
ENV_TOOLS = {"setfenv", "getfenv"}
REGISTER_METHODS = {"RegisterEvent", "RegisterUnitEvent", "RegisterEventCallback"}
URL_RE = re.compile(r"(?:https?://|www\.)[^\s\"'<>|]+|discord(?:app)?\.(?:gg|com/invite)/[\w-]+", re.I)
SCRAMBLED_RE = re.compile(r"^(?:[Il1]{6,}|_0x[0-9a-fA-F]{3,}|[lI][lI1_]{7,}|O0{4,}|[_]{4,}\w*)$")
ESCAPES_RE = re.compile(r"(?:\\(?:\d{1,3}|x[0-9a-fA-F]{2})){24,}")
XML_SCRIPT_RE = re.compile(r"<\s*(Script|On[A-Z]\w*)\b([^>]*)>(.*?)</\s*\1\s*>", re.S)
XML_FILE_REF_RE = re.compile(r"<\s*(?:Script|Include)\b[^>]*?\bfile\s*=\s*[\"']([^\"']+)[\"']", re.I)
SENSITIVE_NAMES = set(rules.API_CAPABILITY) | rules.SENSITIVE_HOOK_TARGETS
SENSITIVE_CAPS = {"money", "chat", "code", "sabotage"}
FRIEND_LIST_APIS = {
    "BNGetNumFriends",
    "BNGetFriendInfo",
    "C_BattleNet.GetFriendAccountInfo",
    "C_FriendList.GetFriendInfoByIndex",
    "C_FriendList.GetNumFriends",
}


class ScanError(Exception):
    pass


@dataclass
class Evidence:
    file: str
    line: int
    detail: str
    snippet: str = ""


@dataclass
class Hit:
    id: str
    evidence: list[Evidence] = field(default_factory=list)


@dataclass
class Unit:
    """A piece of Lua: a .lua file or an inline script inside an .xml file."""

    path: str
    source: str
    line_offset: int = 0
    scan: FileScan | None = None
    lines: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- input


@dataclass
class Package:
    name: str
    files: dict[str, bytes]
    hits: list[Hit]
    entries: int
    total_bytes: int


def _safe_member(name: str) -> tuple[str, bool]:
    """Normalised path and whether it escapes the extraction folder."""
    raw = name.replace("\\", "/")
    escapes = raw.startswith("/") or bool(re.match(r"^[A-Za-z]:", raw)) or ".." in raw.split("/")
    norm = posixpath.normpath(raw.lstrip("/")) if raw.strip("/") else raw
    return norm, escapes


def read_zip(data: bytes, name: str = "addon.zip") -> Package:
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as e:
        raise ScanError(f"not a valid zip file: {e}") from e
    infos = zf.infolist()
    if len(infos) > MAX_ENTRIES:
        raise ScanError(f"too many files in the zip ({len(infos)})")
    files: dict[str, bytes] = {}
    hits: dict[str, Hit] = {}
    total = 0

    def hit(rule: str, path: str, detail: str) -> None:
        hits.setdefault(rule, Hit(rule)).evidence.append(Evidence(path, 0, detail))

    for info in infos:
        path, escapes = _safe_member(info.filename)
        if escapes:
            hit("PKG_PATH_TRAVERSAL", info.filename, "path leaves the folder")
        mode = info.external_attr >> 16
        if stat.S_ISLNK(mode):
            hit("PKG_PATH_TRAVERSAL", info.filename, "symbolic link")
            continue
        if info.is_dir():
            continue
        _classify_name(path, hit)
        total += info.file_size
        if total > MAX_TOTAL_BYTES:
            raise ScanError("the zip unpacks to more than 300 MB; refusing to scan it")
        if info.file_size > 10 * 1024 * 1024 and info.compress_size and info.file_size / info.compress_size > MAX_RATIO:
            raise ScanError(f"{info.filename} looks like a zip bomb (compression ratio over {MAX_RATIO})")
        if info.flag_bits & 0x1:
            hit("PKG_ENCRYPTED", path, "password protected")
            continue
        if _wanted(path) and info.file_size <= MAX_FILE_BYTES:
            try:
                files[path] = zf.read(info)
            except (zipfile.BadZipFile, NotImplementedError, OSError, EOFError) as e:
                raise ScanError(f"cannot read {info.filename}: {e}") from e
    return Package(name, files, list(hits.values()), sum(1 for i in infos if not i.is_dir()), total)


def read_folder(root: Path) -> Package:
    files: dict[str, bytes] = {}
    hits: dict[str, Hit] = {}
    total = count = 0

    def hit(rule: str, path: str, detail: str) -> None:
        hits.setdefault(rule, Hit(rule)).evidence.append(Evidence(path, 0, detail))

    ignored = _pkgmeta_ignores(root)
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root).as_posix()
        # A source checkout: skip what the packager leaves out of the download (.git, .github, .pkgmeta "ignore").
        if any(part.startswith(".") for part in p.relative_to(root).parts) or any(
            rel == ig or rel.startswith(ig.rstrip("/") + "/") for ig in ignored
        ):
            continue
        count += 1
        if p.is_symlink():
            hit("PKG_PATH_TRAVERSAL", rel, "symbolic link")
            continue
        if not p.is_file():
            continue
        _classify_name(rel, hit)
        size = p.stat().st_size
        total += size
        if _wanted(rel) and size <= MAX_FILE_BYTES:
            files[rel] = p.read_bytes()
    return Package(root.name, files, list(hits.values()), count, total)


def _pkgmeta_ignores(root: Path) -> list[str]:
    """Paths listed under ``ignore:`` in the BigWigs/CurseForge packager's .pkgmeta."""
    meta = root / ".pkgmeta"
    if not meta.is_file():
        return []
    out, inside = [], False
    for raw in meta.read_text(encoding="utf-8", errors="replace").splitlines():
        if re.match(r"^ignore\s*:", raw):
            inside = True
            continue
        if inside:
            m = re.match(r"^\s+-\s*(.+?)\s*$", raw)
            if m:
                out.append(m.group(1).strip("'\"").rstrip("/"))
            elif raw.strip() and not raw.startswith((" ", "\t")):
                inside = False
    return out


def _wanted(path: str) -> bool:
    return path.lower().endswith((".lua", ".xml", ".toc"))


def _classify_name(path: str, hit) -> None:
    lower = path.lower()
    base = posixpath.basename(lower)
    ext = posixpath.splitext(base)[1]
    # "readme.txt.exe" style double extensions are covered: only the last one counts.
    if ext in rules.EXECUTABLE_EXTENSIONS:
        hit("PKG_EXECUTABLE", path, ext)
    elif ext in rules.SCRIPT_EXTENSIONS:
        hit("PKG_SCRIPT", path, ext)
    elif ext in rules.ARCHIVE_EXTENSIONS:
        hit("PKG_NESTED_ARCHIVE", path, ext)
    elif ext and ext not in rules.ADDON_EXTENSIONS and base not in ("license", "readme", "changelog", "copying", "authors"):
        hit("PKG_UNUSUAL_FILE", path, ext)


# --------------------------------------------------------------------------- units


def _decode(data: bytes) -> str:
    return data.decode("utf-8-sig", errors="replace")


def build_units(files: dict[str, bytes]) -> list[Unit]:
    units: list[Unit] = []
    for path, data in sorted(files.items()):
        lower = path.lower()
        if lower.endswith(".lua"):
            units.append(Unit(path, _decode(data)))
        elif lower.endswith(".xml"):
            text = _decode(data)
            text_nc = re.sub(r"<!--.*?-->", lambda m: "\n" * m.group(0).count("\n"), text, flags=re.S)
            for k, m in enumerate(XML_SCRIPT_RE.finditer(text_nc), 1):
                body = m.group(3)
                if not body.strip():
                    continue
                # Keep every newline so line numbers match the .xml file; only drop the CDATA markers.
                body = body.replace("<![CDATA[", "         ").replace("]]>", "   ")
                line = text_nc.count("\n", 0, m.start(3)) + 1
                units.append(Unit(f"{path}#{m.group(1)}{k}", _xml_unescape(body), line - 1))
    for u in units:
        u.scan = scan(u.path, u.source)
        u.lines = u.source.split("\n")  # same line numbering as the lexer (\r is stripped in snippets)
    return units


def _xml_unescape(s: str) -> str:
    return s.replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"').replace("&apos;", "'").replace("&amp;", "&")


def _ev(u: Unit, tok: Token, detail: str) -> Evidence:
    line = tok.line
    text = u.lines[line - 1].strip() if 0 < line <= len(u.lines) else ""
    if len(text) > 160:
        start = max(0, tok.col - 60)
        text = ("…" if start else "") + text[start : start + 150] + "…"
    return Evidence(u.path.split("#")[0], line + u.line_offset, detail, text)


# --------------------------------------------------------------------------- per-unit facts


@dataclass
class Facts:
    caps: dict[str, list[Evidence]] = field(default_factory=lambda: defaultdict(list))
    hits: dict[str, Hit] = field(default_factory=dict)
    # per unit flags used by the combination rules
    remote_input: set[str] = field(default_factory=set)  # unit paths that listen to other players
    dynamic_code: dict[str, list[Evidence]] = field(default_factory=lambda: defaultdict(list))  # non-template
    template_code: dict[str, list[Evidence]] = field(default_factory=lambda: defaultdict(list))  # code from the file's own strings
    obfuscated: set[str] = field(default_factory=set)
    hiding: dict[str, list[Evidence]] = field(default_factory=lambda: defaultdict(list))
    money_units: set[str] = field(default_factory=set)
    overrides: list[Evidence] = field(default_factory=list)
    urls: dict[str, Evidence] = field(default_factory=dict)
    own_dialogs: set[str] = field(default_factory=set)  # StaticPopupDialogs keys the addon creates itself

    def hit(self, rule: str, ev: Evidence) -> None:
        h = self.hits.setdefault(rule, Hit(rule))
        if len(h.evidence) < 50 and not any(e.file == ev.file and e.line == ev.line and e.detail == ev.detail for e in h.evidence):
            h.evidence.append(ev)


def analyse_unit(u: Unit, facts: Facts, addon_defines: set[str]) -> None:
    s = u.scan
    assert s is not None
    toks = s.tokens
    n = len(toks)
    key = u.path.split("#")[0]  # inline XML scripts of one file count as one file

    # Capabilities from global references (the scope scan already ignores locals).
    for r in s.refs:
        name = r.name if r.name in rules.API_CAPABILITY else r.name.split(".", 1)[0]
        cap = rules.API_CAPABILITY.get(name)
        if cap is None or name in addon_defines - SENSITIVE_NAMES:
            continue
        ev = _ev(u, r.tok, name)
        if len(facts.caps[cap]) < 40:
            facts.caps[cap].append(ev)
        if cap == "money":
            facts.money_units.add(key)
        if name in CODE_RUNNERS and r.is_call:
            if _template_argument(toks, r.end, u):
                facts.template_code[key].append(ev)
                continue
            facts.dynamic_code[key].append(ev)
            facts.hit("DYNAMIC_CODE", ev)
        if cap == "sabotage":
            facts.hit("GUILD_DISBAND" if name == "GuildDisband" else "SABOTAGE", ev)
        if cap == "macros" and name in ("CreateMacro", "EditMacro"):
            facts.hit("MACRO_WRITE", ev)

    for k, t in enumerate(toks):
        nxt = toks[k + 1] if k + 1 < n else None
        nxt2 = toks[k + 2] if k + 2 < n else None
        prev = toks[k - 1] if k else None

        if t.kind == NAME:
            # Event registration: frame:RegisterEvent("CHAT_MSG_ADDON"), self:RegisterComm("prefix")
            if t.value in REGISTER_METHODS and nxt is not None and nxt.is_op("(") and nxt2 is not None:
                arg = nxt2 if nxt2.kind == STRING else (toks[k + 4] if k + 4 < n and toks[k + 3].is_op(",") else None)
                if arg is not None and arg.kind == STRING and arg.value in rules.REMOTE_INPUT_EVENTS:
                    facts.remote_input.add(key)
            if t.value == "RegisterComm" and prev is not None and prev.is_op(":"):
                facts.remote_input.add(key)
            if t.value == "RegisterAddonMessagePrefix":
                facts.remote_input.add(key)

            # Chat filters that hide money, loot or whispers
            if (
                t.value.endswith("AddMessageEventFilter")
                and nxt is not None
                and nxt.is_op("(")
                and nxt2 is not None
                and nxt2.kind == STRING
            ):
                if nxt2.value in rules.HIDING_FILTER_EVENTS:
                    ev = _ev(u, t, nxt2.value)
                    facts.hit("HIDING_FILTER", ev)
                    facts.hiding[key].append(ev)

            # hooksecurefunc("Name", fn) / hooksecurefunc(tbl, "Name", fn)
            if t.value == "hooksecurefunc" and nxt is not None and nxt.is_op("("):
                target = None
                if nxt2 is not None and nxt2.kind == STRING:
                    target = nxt2.value
                elif nxt2 is not None and nxt2.kind == NAME and k + 4 < n and toks[k + 3].is_op(",") and toks[k + 4].kind == STRING:
                    target = f"{nxt2.value}.{toks[k + 4].value}"
                if target and (target in rules.SENSITIVE_HOOK_TARGETS or target.split(".")[-1] in rules.SENSITIVE_HOOK_TARGETS):
                    ev = _ev(u, t, target)
                    facts.hit("SENSITIVE_HOOK", ev)

            # Blizzard confirmation windows: StaticPopup1Button1:Click(), TradeFrame:Hide(), ...:SetScript
            if t.value.startswith(rules.SENSITIVE_FRAME_PREFIXES) and (prev is None or not prev.is_op(".", ":")):
                j = k + 1
                while j + 1 < n and toks[j].is_op(".") and toks[j + 1].kind == NAME:
                    j += 2
                method = toks[j + 1].value if j + 1 < n and toks[j].is_op(":") and toks[j + 1].kind == NAME else ""
                direct = j == k + 1  # TradeFrame:Hide(), not TradeFrame.Portrait:SetAlpha(0) (skins do that)
                if method in ("Click", "SetScript", "HookScript") or (direct and method in ("Hide", "SetAlpha", "SetShown", "EnableMouse")):
                    ev = _ev(u, t, f"{t.value}:{toks[j + 1].value}")
                    facts.hit("SENSITIVE_FRAME", ev)
                    facts.hiding[key].append(ev)

            # StaticPopupDialogs["EXISTING"].OnAccept = ... (changing a Blizzard dialog, not one the addon creates)
            if t.value == "StaticPopupDialogs" and nxt is not None and nxt.is_op("["):
                close = _closing(toks, k + 1)
                dialog = _literal_string(toks[k + 2 : close])
                if (
                    close + 3 < n
                    and toks[close + 1].is_op(".")
                    and toks[close + 2].kind == NAME
                    and toks[close + 3].is_op("=")
                    and dialog not in facts.own_dialogs
                ):
                    ev = _ev(u, t, f"StaticPopupDialogs[…].{toks[close + 2].value}")
                    facts.hit("SENSITIVE_FRAME", ev)
                    facts.hiding[key].append(ev)

            # _G[...] / getglobal(...) / rawget(_G, ...)
            if t.value == "_G" and nxt is not None and nxt.is_op("["):
                close = _closing(toks, k + 1)
                inner = toks[k + 2 : close]
                literal = _literal_string(inner)
                if literal is not None:
                    _named_access(u, facts, t, literal, toks, close, addon_defines)
                elif close + 1 < n and toks[close + 1].is_op("("):  # _G[name](...): calls a function chosen at runtime
                    facts.hit("INDIRECT_GLOBAL", _ev(u, t, "_G[…](…)"))

            # Replacing a sensitive Blizzard function: GetMoney = function ... / C_AuctionHouse.PlaceBid = ...
            if (prev is None or not prev.is_op(".", ":", ",")) and not (prev is not None and prev.is_kw("local")):
                full, j = _dotted(toks, k)
                if full in rules.SENSITIVE_HOOK_TARGETS and j < n and toks[j].is_op("="):
                    if not _is_local(s, full) and not _polyfill(toks, j, full):
                        ev = _ev(u, t, full)
                        facts.hit("BLIZZARD_OVERRIDE_SENSITIVE", ev)
                        facts.overrides.append(ev)
                        facts.hiding[key].append(ev)

            # string.char(83, 101, ...) spelling a sensitive name
            if t.value == "char" and prev is not None and prev.is_op(".", ":") and nxt is not None and nxt.is_op("("):
                close = _closing(toks, k + 1)
                nums = [x for x in toks[k + 2 : close] if x.kind == NUMBER]
                if nums and len(nums) * 2 - 1 == close - k - 2:
                    try:
                        text = "".join(chr(int(x.value, 0)) for x in nums)
                    except (ValueError, OverflowError):
                        text = ""
                    if text in SENSITIVE_NAMES:
                        facts.hit("BUILT_API_NAME", _ev(u, t, f"string.char → {text}"))

        elif t.kind == STRING:
            # "Send" .. "Mail"
            if nxt is not None and nxt.is_op("..") and (prev is None or not prev.is_op("..")):
                parts, j = [t.value], k
                while j + 2 < n and toks[j + 1].is_op("..") and toks[j + 2].kind == STRING:
                    parts.append(toks[j + 2].value)
                    j += 2
                joined = "".join(parts)
                if len(parts) > 1 and joined in SENSITIVE_NAMES:
                    facts.hit("BUILT_API_NAME", _ev(u, t, " .. ".join(f'"{p}"' for p in parts) + f" → {joined}"))
            # ("liaMdneS"):reverse()
            if nxt is not None and nxt.is_op(")") and nxt2 is not None and nxt2.is_op(":") and k + 3 < n and toks[k + 3].value == "reverse":
                if t.value[::-1] in SENSITIVE_NAMES:
                    facts.hit("BUILT_API_NAME", _ev(u, t, f'"{t.value}":reverse() → {t.value[::-1]}'))
            for m in URL_RE.finditer(t.value):
                url = m.group(0).rstrip(".,;)")
                facts.urls.setdefault(url.lower(), _ev(u, t, url))

    _obfuscation(u, facts)


def _created_dialogs(toks: list[Token]) -> set[str]:
    """Keys of ``StaticPopupDialogs["KEY"] = { ... }``: dialogs the addon defines for itself."""
    out = set()
    for k, t in enumerate(toks):
        if t.kind == NAME and t.value == "StaticPopupDialogs" and k + 1 < len(toks) and toks[k + 1].is_op("["):
            close = _closing(toks, k + 1)
            key = _literal_string(toks[k + 2 : close])
            if key and close + 2 < len(toks) and toks[close + 1].is_op("=") and toks[close + 2].is_op("{"):
                out.add(key)
    return out


def _named_access(u: Unit, facts: Facts, tok: Token, name: str, toks: list[Token], close: int, addon_defines: set[str]) -> None:
    key = u.path.split("#")[0]
    cap = rules.API_CAPABILITY.get(name)
    if cap:
        ev = _ev(u, tok, f'_G["{name}"]')
        if len(facts.caps[cap]) < 40:
            facts.caps[cap].append(ev)
        if cap == "money":
            facts.money_units.add(key)
        if name in CODE_RUNNERS:
            facts.dynamic_code[key].append(ev)
            facts.hit("DYNAMIC_CODE", ev)
    if name in rules.SENSITIVE_HOOK_TARGETS and close + 1 < len(toks) and toks[close + 1].is_op("="):
        if not _polyfill(toks, close + 1, name):
            ev = _ev(u, tok, f'_G["{name}"] =')
            facts.hit("BLIZZARD_OVERRIDE_SENSITIVE", ev)
            facts.overrides.append(ev)
            facts.hiding[key].append(ev)


def _dotted(toks: list[Token], k: int) -> tuple[str, int]:
    parts = [toks[k].value]
    j = k + 1
    while j + 1 < len(toks) and toks[j].is_op(".") and toks[j + 1].kind == NAME:
        parts.append(toks[j + 1].value)
        j += 2
    return ".".join(parts[:2]), j


def _is_local(s: FileScan, name: str) -> bool:
    # A global reference of the same name exists in the scan only if it is not a local.
    return not any(r.name == name or r.name.split(".", 1)[0] == name.split(".", 1)[0] for r in s.refs) and name not in s.defines


def _polyfill(toks: list[Token], eq: int, name: str) -> bool:
    """``Name = Name or function ...`` keeps Blizzard's version when it exists."""
    rhs, j = _dotted(toks, eq + 1) if eq + 1 < len(toks) and toks[eq + 1].kind == NAME else ("", eq + 1)
    return rhs == name and j < len(toks) and toks[j].is_kw("or")


def _closing(toks: list[Token], open_index: int) -> int:
    depth = 0
    for k in range(open_index, len(toks)):
        if toks[k].is_op("(", "[", "{"):
            depth += 1
        elif toks[k].is_op(")", "]", "}"):
            depth -= 1
            if depth == 0:
                return k
    return len(toks) - 1


def _literal_string(tokens: list[Token]) -> str | None:
    if tokens and all(t.kind == STRING or t.is_op("..") for t in tokens) and tokens[0].kind == STRING:
        return "".join(t.value for t in tokens if t.kind == STRING)
    return None


_TEMPLATE_FUNCS = {"format", "gsub", "rep", "tostring", "concat", "join", "upper", "lower", "sub", "string", "table", "strjoin", "assert"}


def _template_argument(toks: list[Token], open_index: int, u: Unit) -> bool:
    """True when the code passed to loadstring comes from the file itself (a template), not from outside.

    Accepts string literals, numbers, string functions applied to them, and locals that this file
    assigns from a string literal (CallbackHandler's dispatcher template is the common case).
    """
    if open_index >= len(toks):
        return False
    if toks[open_index].kind == STRING:  # loadstring "code"
        return True
    if not toks[open_index].is_op("("):
        return False
    close = _closing(toks, open_index)
    depth = 0
    first_arg: list[Token] = []
    for t in toks[open_index + 1 : close]:
        if t.is_op("(", "[", "{"):
            depth += 1
        elif t.is_op(")", "]", "}"):
            depth -= 1
        elif depth == 0 and t.is_op(","):
            break
        first_arg.append(t)
    if not first_arg:
        return False
    if first_arg[0].kind == STRING:  # "return _G['" .. name .. "']" : the shape of the code is the author's
        return True
    after_colon = False
    for t in first_arg:
        if t.kind in (STRING, NUMBER) or t.kind == OP:
            after_colon = t.is_op(":", ".")
            continue
        if t.kind == NAME:
            if after_colon or t.value in _TEMPLATE_FUNCS:
                after_colon = False
                continue
            if not _assigned_from_literal(toks, t.value):
                return False
        after_colon = False
    return True


def _assigned_from_literal(toks: list[Token], name: str) -> bool:
    seen = False
    for k in range(len(toks) - 2):
        if toks[k].kind == NAME and toks[k].value == name and toks[k + 1].is_op("=") and (k == 0 or not toks[k - 1].is_op(".", ":")):
            seen = True
            rhs = toks[k + 2]
            if rhs.kind == STRING:
                continue
            if rhs.kind == NAME and rhs.value == name and k + 3 < len(toks) and toks[k + 3].is_op(":", ".."):
                continue  # code = code:gsub(...) / code = code .. "x"
            if rhs.is_op("(") and k + 3 < len(toks) and toks[k + 3].kind == STRING:
                continue
            if rhs.kind == NAME and rhs.value in ("format", "string"):
                continue
            return False
    return seen


def _entropy(s: str) -> float:
    if not s:
        return 0.0
    counts = Counter(s)
    total = len(s)
    return -sum(c / total * math.log2(c / total) for c in counts.values())


def _obfuscation(u: Unit, facts: Facts) -> None:
    s = u.scan
    assert s is not None
    toks = s.tokens
    signals: list[tuple[Token | None, str]] = []
    for t in toks:
        if t.kind == STRING and len(t.value) >= 400 and _entropy(t.value) >= 5.2:
            signals.append((t, f"encoded string of {len(t.value)} characters (entropy {_entropy(t.value):.1f})"))
    escapes = ESCAPES_RE.findall(u.source)
    if escapes:
        signals.append((None, f"{len(escapes)} string(s) written as escaped character codes"))
    scrambled = {t.value for t in toks if t.kind == NAME and SCRAMBLED_RE.match(t.value)}
    if len(scrambled) >= 8:
        signals.append((None, f"{len(scrambled)} scrambled names (e.g. {', '.join(sorted(scrambled)[:3])})"))
    # long runs of byte values: { 72, 101, 108, ... }
    run = best = 0
    run_start = best_tok = None
    for t in toks:
        if t.kind == NUMBER and _byte(t.value):
            run += 1
            if run == 1:
                run_start = t
            if run > best:
                best, best_tok = run, run_start
        elif not t.is_op(","):
            run = 0
    if best >= 300:
        signals.append((best_tok, f"table of {best} byte values"))
    names = {t.value for t in toks if t.kind == NAME}
    if {"bxor"} & names and {"byte", "char"} <= names:
        signals.append((None, "XOR decoding (bxor with byte/char)"))
    longest = max((len(line) for line in u.lines), default=0)
    code_tokens = sum(1 for t in toks if t.kind in (NAME, OP))
    if longest >= 8000 and code_tokens > 2000 and len(u.lines) < 20:
        signals.append((None, f"minified code (a line of {longest} characters)"))
    # One strong signal, or two different weaker ones (many encoded strings alone are usually import data).
    kinds = {d.split(" ")[0] if not d.startswith("encoded") else "encoded" for _, d in signals}
    strong = any("escaped" in d or "byte values" in d or "scrambled" in d or "minified" in d for _, d in signals)
    if strong or len(kinds) >= 2:
        facts.obfuscated.add(u.path.split("#")[0])
        for tok, detail in signals[:4]:
            if tok is not None:
                facts.hit("OBFUSCATION", _ev(u, tok, detail))
            else:
                facts.hit("OBFUSCATION", Evidence(u.path.split("#")[0], 1 + u.line_offset, detail))


def _byte(text: str) -> bool:
    try:
        return 0 <= int(text, 0) <= 255
    except ValueError:
        return False


# --------------------------------------------------------------------------- package-level


def toc_info(files: dict[str, bytes]) -> tuple[list[dict], set[str], bool]:
    """TOC metadata, the files any TOC/XML loads, and whether any TOC declares SavedVariables."""
    tocs = []
    loaded: set[str] = set()
    saved = False
    lower = {p.lower(): p for p in files}
    for path, data in files.items():
        if not path.lower().endswith(".toc"):
            continue
        meta: dict = {"file": path}
        base = posixpath.dirname(path)
        for raw in _decode(data).splitlines():
            line = raw.strip()
            if line.startswith("##"):
                key, _, value = line[2:].partition(":")
                key = key.strip().lower()
                if key in ("title", "author", "version", "interface", "notes"):
                    meta.setdefault(key, re.sub(r"\|c[0-9a-fA-F]{8}|\|r", "", value.strip())[:120])
                if key.startswith("savedvariables"):
                    saved = saved or bool(value.strip())
            elif line and not line.startswith("#"):
                entry = re.sub(r"(\s*\[[^\]]*\])+\s*$", "", line).replace("\\", "/")
                entry = entry.replace("[Family]", "*").replace("[Game]", "*").replace("[TextLocale]", "*")
                _mark_loaded(posixpath.normpath(posixpath.join(base, entry)), lower, files, loaded)
        tocs.append(meta)
    return tocs, loaded, saved


def _mark_loaded(path: str, lower: dict[str, str], files: dict[str, bytes], loaded: set[str]) -> None:
    if "*" in path:
        rx = re.compile("^" + re.escape(path.lower()).replace(r"\*", "[^/]*") + "$")
        for low, real in lower.items():
            if rx.match(low):
                _mark_loaded(real, lower, files, loaded)
        return
    real = lower.get(path.lower())
    if real is None or real in loaded:
        return
    loaded.add(real)
    if real.lower().endswith(".xml"):
        text = re.sub(r"<!--.*?-->", "", _decode(files[real]), flags=re.S)
        for ref in XML_FILE_REF_RE.findall(text):
            _mark_loaded(posixpath.normpath(posixpath.join(posixpath.dirname(real), ref.replace("\\", "/"))), lower, files, loaded)


# --------------------------------------------------------------------------- report


@dataclass
class Report:
    target: str
    severity: str
    capabilities: dict[str, list[Evidence]]
    findings: list[Hit]
    addons: list[dict]
    stats: dict

    def to_dict(self, lang: str = "es") -> dict:
        return {
            "tool": {"name": "addon-sentry", "version": __version__},
            "target": self.target,
            "verdict": {"level": self.severity, "text": rules.VERDICTS[self.severity][lang]},
            "addons": self.addons,
            "capabilities": [
                {"id": cap, "text": rules.CAPABILITIES[cap][lang], "evidence": [e.__dict__ for e in evs[:12]], "count": len(evs)}
                for cap, evs in self.capabilities.items()
                if evs
            ],
            "findings": [
                {
                    "id": h.id,
                    "severity": rules.FINDINGS[h.id]["severity"],
                    "severity_text": rules.SEVERITY_NAMES[lang][rules.FINDINGS[h.id]["severity"]],
                    "title": rules.FINDINGS[h.id][lang][0],
                    "explanation": rules.FINDINGS[h.id][lang][1],
                    "evidence": [e.__dict__ for e in h.evidence[:20]],
                    "count": len(h.evidence),
                }
                for h in self.findings
            ],
            "stats": self.stats,
            "disclaimer": rules.DISCLAIMER[lang],
        }


def analyse(pkg: Package) -> Report:
    units = build_units(pkg.files)
    addon_defines: set[str] = set()
    for u in units:
        addon_defines |= u.scan.defines if u.scan else set()
    facts = Facts()
    for h in pkg.hits:
        for e in h.evidence:
            facts.hit(h.id, e)
    tocs, loaded, saved = toc_info(pkg.files)
    # WoW only runs Lua that a .toc lists or an .xml includes. Without any .toc, check everything.
    runs = [u for u in units if not tocs or u.path.split("#")[0] in loaded]
    for u in runs:
        facts.own_dialogs |= _created_dialogs(u.scan.tokens)
    for u in runs:
        analyse_unit(u, facts, addon_defines)

    if not tocs and units:
        facts.hit("PKG_NO_TOC", Evidence(pkg.name, 0, "no .toc"))
    if tocs:
        for path in sorted(p for p in pkg.files if p.lower().endswith(".lua") and p not in loaded):
            facts.hit("PKG_UNLOADED_LUA", Evidence(path, 0, "not listed"))

    findings, top = _combine(facts, saved)
    addons = [{k: v for k, v in t.items()} for t in sorted(tocs, key=lambda t: t["file"])]
    stats = {
        "files": pkg.entries,
        "bytes": pkg.total_bytes,
        "lua_files": sum(1 for p in pkg.files if p.lower().endswith(".lua")),
        "xml_scripts": sum(1 for u in units if "#" in u.path),
        "lines": sum(len(u.lines) for u in units),
    }
    caps = {c: facts.caps.get(c, []) for c in rules.CAPABILITIES}
    return Report(pkg.name, top, caps, findings, addons, stats)


def _combine(facts: Facts, saved: bool) -> tuple[list[Hit], str]:
    """Rules that need several facts together, then sort the findings."""
    for path in facts.dynamic_code:
        if path in facts.remote_input:
            for ev in facts.dynamic_code[path][:3]:
                facts.hit("REMOTE_CODE", ev)
        elif facts.remote_input:
            for ev in facts.dynamic_code[path][:3]:
                facts.hit("LISTENS_AND_RUNS", ev)

    for path in sorted(facts.obfuscated):
        # Encoded code that gets run: a template does not excuse it when the "template" itself is hidden.
        for ev in (facts.dynamic_code.get(path, []) + facts.template_code.get(path, []))[:3]:
            facts.hit("OBFUSCATED_LOADER", ev)
    if facts.overrides and facts.caps.get("money"):
        for ev in facts.overrides[:5]:
            facts.hit("HIDDEN_MONEY", ev)
    elif facts.caps.get("money") and any(path in facts.money_units for path in facts.hiding):
        for path, evs in facts.hiding.items():
            if path in facts.money_units:
                for ev in evs[:3]:
                    facts.hit("MONEY_AND_HIDING", ev)
    account_sensitive = [e for e in facts.caps.get("account", []) if e.detail in FRIEND_LIST_APIS]
    if account_sensitive and facts.caps.get("chat"):
        for ev in account_sensitive[:5]:
            facts.hit("EXFILTRATION", ev)
    stats_reads = [e for e in facts.caps.get("profiling", []) if e.detail in ("GetComparisonStatistic", "SetAchievementComparisonUnit")]
    if stats_reads and saved:
        for ev in stats_reads[:5]:
            facts.hit("PROFILING", ev)
    if facts.urls:
        for ev in list(facts.urls.values())[:30]:
            facts.hit("URL", ev)

    order = {s: i for i, s in enumerate(rules.SEVERITIES)}
    findings = sorted(facts.hits.values(), key=lambda h: (-order[rules.FINDINGS[h.id]["severity"]], h.id))
    top = max((rules.FINDINGS[h.id]["severity"] for h in findings), key=lambda s: order[s], default="info")
    return findings, top


def scan_path(path: str | Path) -> Report:
    p = Path(path)
    if p.is_dir():
        return analyse(read_folder(p))
    return analyse(read_zip(p.read_bytes(), p.name))


def scan_bytes(data: bytes, name: str = "addon.zip") -> Report:
    return analyse(read_zip(data, name))


# --------------------------------------------------------------------------- WeakAuras strings


def scan_aura(text: str) -> Report:
    """Scans the Lua inside a WeakAuras import string, without importing or running it."""
    try:
        exp = auras.read(text)
    except auras.AuraError as e:
        raise ScanError(str(e)) from e
    units = []
    for c in exp.code:
        # "#" separates inline scripts from their file elsewhere in the engine; keep it out of the label.
        units.append(Unit(f"{c.aura.replace('#', '＃')} › {c.path}", c.code))
    for u in units:
        u.scan = scan(u.path, u.source)
        u.lines = u.source.split("\n")
    facts = Facts()
    for u in units:
        facts.own_dialogs |= _created_dialogs(u.scan.tokens)
    for u in units:
        analyse_unit(u, facts, set())
        for r in u.scan.refs:
            name = r.name if r.name in rules.AURA_BLOCKED else r.name.split(".", 1)[0]
            if name in rules.AURA_BLOCKED:
                facts.hit("AURA_BLOCKED", _ev(u, r.tok, name))
    for aura, path, detail in exp.chat:
        if len(facts.caps["chat"]) < 40:
            facts.caps["chat"].append(Evidence(f"{aura.replace('#', '＃')} › {path}", 0, detail))
    findings, top = _combine(facts, False)
    meta = {"file": f"WeakAuras ({exp.format})", "title": exp.auras[0][:120]}
    if exp.addon_version:
        meta["version"] = f"WeakAuras {exp.addon_version[:40]}"
    if exp.urls:
        meta["url"] = exp.urls[0][:200]
    stats = {
        "auras": len(exp.auras),
        "code_pieces": len(units),
        "bytes": len(text.encode("utf-8")),
        "lines": sum(len(u.lines) for u in units),
    }
    caps = {c: facts.caps.get(c, []) for c in rules.CAPABILITIES}
    return Report(exp.auras[0], top, caps, findings, [meta], stats)
