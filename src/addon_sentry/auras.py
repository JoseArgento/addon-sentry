"""Reads WeakAuras import strings and pulls out the Lua they carry.

A WeakAuras export is ``!WA:2!`` + LibDeflate:EncodeForPrint(LibDeflate:CompressDeflate(
LibSerialize:Serialize(transmit))). Older strings start with a single ``!`` and use
AceSerializer instead of LibSerialize. This module decodes both without running anything
(the formats are re-implemented here from LibDeflate, LibSerialize and AceSerializer-3.0),
then walks the aura tables for the fields WeakAuras compiles as code.

The oldest strings (2016-2018: no ``!``) are WeakAuras' own 6-bit encoding + LibCompress
(LZW or Huffman) + AceSerializer, also decoded here.
"""

from __future__ import annotations

import math
import re
import struct
import zlib
from dataclasses import dataclass, field

MAX_INPUT_CHARS = 8 * 1024 * 1024
MAX_INFLATED = 64 * 1024 * 1024
MAX_OBJECTS = 2_000_000
MAX_DEPTH = 120

_ALPHABET = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789()"
_SIX = {ord(c): i for i, c in enumerate(_ALPHABET)}
_LUA_SPACE = "".join(chr(c) for c in list(range(32)) + [127]) + " "  # Lua's [%c ]

# Fields WeakAuras turns into functions (WeakAurasOptions/OptionsFrames/Update.lua lists the same ones
# for its own import review). Matched by key name anywhere in an aura, so a field in an unexpected
# place is still scanned.
CODE_KEYS = frozenset(
    ["custom", "customVariables", "customDuration", "customName", "customIcon", "customTexture", "customStacks"]
    + [f"customOverlay{i}" for i in range(1, 8)]
    + ["customText", "customAnchor", "customGrow", "customSort", "customAnchorPerUnit", "customTriggerLogic"]
    + ["customOnLoad", "customOnUnload", "message_custom"]
    + ["alphaFunc", "translateFunc", "scaleFunc", "rotateFunc", "colorFunc"]
)
# Other keys that look like code holders (a newer WeakAuras field, or one we do not know).
_GENERIC_KEY = re.compile(r"custom|func\Z", re.I)
_CODE_LIKE = re.compile(r"(?<![A-Za-z0-9_])(?:function|return)(?![A-Za-z0-9_])")
# Lua numbers as tostring() writes them; anything else is rejected (the JavaScript port uses the same patterns).
_DEC = re.compile(r"[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?")
_HEX = re.compile(r"[+-]?0[xX][0-9a-fA-F]+")
SEND_CHAT_TYPES = frozenset(
    ["WHISPER", "SAY", "EMOTE", "YELL", "PARTY", "GUILD", "OFFICER", "RAID", "SMARTRAID", "RAID_WARNING", "INSTANCE_CHAT"]
)


class AuraError(Exception):
    pass


class LuaBool:
    """A boolean used as a table key. Python would merge t[True] with t[1]; Lua keeps them apart."""

    __slots__ = ("value",)

    def __init__(self, value: bool):
        self.value = value

    def __repr__(self) -> str:
        return "true" if self.value else "false"


LUA_TRUE, LUA_FALSE = LuaBool(True), LuaBool(False)


class LuaTable(dict):
    """A Lua table. dict keeps insertion order; identity (not equality) matters for references."""

    __slots__ = ()

    def __hash__(self) -> int:  # tables can be keys in Lua
        return id(self)

    def __eq__(self, other) -> bool:
        return self is other


# --------------------------------------------------------------------------- LibDeflate


def decode_for_print(s: str) -> bytes | None:
    s = s.lstrip(_LUA_SPACE).rstrip(_LUA_SPACE)
    if len(s) == 1:
        return None
    out = bytearray()
    i, n = 0, len(s)
    while i + 3 < n:
        x = [_SIX.get(ord(c)) for c in s[i : i + 4]]
        if None in x:
            return None
        cache = x[0] + x[1] * 64 + x[2] * 4096 + x[3] * 262144
        out += bytes((cache & 255, (cache >> 8) & 255, cache >> 16))
        i += 4
    cache = bits = 0
    while i < n:
        x = _SIX.get(ord(s[i]))
        if x is None:
            return None
        cache += x << bits
        bits += 6
        i += 1
    while bits >= 8:
        out.append(cache & 255)
        cache >>= 8
        bits -= 8
    return bytes(out)


def inflate(data: bytes) -> bytes:
    d = zlib.decompressobj(-15)
    try:
        out = d.decompress(data, MAX_INFLATED + 1)
    except zlib.error as e:
        raise AuraError(DAMAGED) from e
    if len(out) > MAX_INFLATED:
        raise AuraError("the string unpacks to more than 64 MB; refusing to read it")
    if not d.eof:
        raise AuraError(DAMAGED)
    # Bytes after the end of the deflate data are ignored, as LibDeflate:DecompressDeflate does.
    return out


DAMAGED = "cannot decompress: the string is damaged or cut short"


# --------------------------------------------------------------------------- version 0: WeakAuras' decodeB64 + LibCompress


def decode_b64_v0(s: str) -> bytes:
    """WeakAuras' decodeB64 (Transmission.lua), step by step: unknown characters count as 0 and it never fails."""
    out = bytearray()
    bits = nbits = 0
    i, n = 0, len(s)
    while True:
        if nbits >= 8:
            out.append(bits & 255)
            bits >>= 8
            nbits -= 8
        bits += (_SIX.get(ord(s[i]), 0) if i < n else 0) << nbits
        nbits += 6
        if i >= n:
            break
        i += 1
    return bytes(out)


def _lc_decode_number(d: bytes, i: int) -> tuple[int, int]:
    a = d[i]
    if a > 249:
        a = 256 - a
        if i + a >= len(d):
            raise AuraError(V0_ERROR)
        r = 0
        for k in range(i + a, i, -1):
            r = r * 255 + d[k] - 1
        return r, a + 1
    return a, 1


def _lc_lzw(d: bytes) -> bytes:
    d = d[1:]
    if not d:
        raise AuraError(V0_ERROR)
    table = {i: bytes((i,)) for i in range(256)}
    size = 256
    k, step = _lc_decode_number(d, 0)
    t = step
    if k not in table:
        raise AuraError(V0_ERROR)
    w = table[k]
    out = bytearray(w)
    while t < len(d):
        k, step = _lc_decode_number(d, t)
        t += step
        entry = table.get(k) or (w + w[:1])
        out += entry
        if len(out) > MAX_INFLATED:
            raise AuraError("the string unpacks to more than 64 MB; refusing to read it")
        table[size] = w + entry[:1]
        size += 1
        w = entry
    return bytes(out)


def _lc_huffman(d: bytes) -> bytes:
    if len(d) < 5:
        raise AuraError(V0_ERROR)
    num_symbols = d[1] + 1
    orig = d[2] + d[3] * 256 + d[4] * 65536
    if orig == 0:
        return b""
    bits = nbits = 0
    i, n, state, symbol = 5, 0, 0, 0
    codes: dict[tuple[int, int], int] = {}
    min_len, max_len = 1000, 0
    while n < num_symbols:
        if i >= len(d):
            raise AuraError(V0_ERROR)
        bits |= d[i] << nbits
        nbits += 8
        if state == 0:
            symbol = bits & 255
            bits >>= 8
            nbits -= 8
            state = 1
        else:
            # a code ends with two set bits in a row (LibCompress getCode2)
            for k in range(nbits - 1):
                if (bits >> k) & 3 == 3:
                    if k > 32:
                        raise AuraError(V0_ERROR)
                    code = bits & ((1 << k) - 1)
                    bits >>= k + 2
                    nbits -= k + 2
                    c, cl = _lc_unescape(code, k)
                    codes[(cl, c)] = symbol
                    min_len, max_len = min(min_len, cl), max(max_len, cl)
                    n += 1
                    state = 0
                    break
        i += 1
    bits &= 0xFFFFFFFF  # the data loop only keeps the low 32 bits
    out = bytearray()
    length = min_len
    while True:
        if length <= nbits:
            sym = codes.get((length, bits & ((1 << length) - 1)))
            if sym is not None:
                out.append(sym)
                if len(out) >= orig:
                    break
                bits >>= length
                nbits -= length
                length = min_len
            else:
                length += 1
                if length > max_len:
                    raise AuraError(V0_ERROR)
        else:
            bits |= (d[i] if i < len(d) else 0) << nbits
            nbits += 8
            if i > len(d):
                break
            i += 1
    return bytes(out)


def _lc_unescape(code: int, code_len: int) -> tuple[int, int]:
    out = pos = i = 0
    while i < code_len:
        if code & (1 << i):
            out |= 1 << pos
            i += 1
        i += 1
        pos += 1
    return out, pos


def libcompress_decompress(d: bytes) -> bytes:
    if not d:
        raise AuraError(V0_ERROR)
    if d[0] == 1:
        return d[1:]
    if d[0] == 2:
        return _lc_lzw(d)
    if d[0] == 3:
        return _lc_huffman(d)
    raise AuraError(V0_ERROR)


V0_ERROR = "this is not a WeakAuras import string (they start with !WA:2!)"


# --------------------------------------------------------------------------- LibSerialize


def _str(b: bytes) -> str:
    return b.decode("utf-8", errors="replace")


class _LSReader:
    def __init__(self, data: bytes):
        self.d = data
        self.p = 0
        self.strings: list[str] = []
        self.tables: list[LuaTable] = []
        self.count = 0
        self.depth = 0

    def bytes(self, n: int) -> bytes:
        if self.p + n > len(self.d):
            raise AuraError("cannot deserialize: data ends early")
        b = self.d[self.p : self.p + n]
        self.p += n
        return b

    def int(self, n: int) -> int:
        return int.from_bytes(self.bytes(n), "big")

    def string(self, n: int) -> str:
        v = _str(self.bytes(n))
        if n > 2:
            self.strings.append(v)
        return v

    def table(self, entries: int, value: LuaTable | None = None) -> LuaTable:
        if value is None:
            value = LuaTable()
            self.tables.append(value)
        for _ in range(entries):
            k = self.obj()
            v = self.obj()
            _set(value, k, v)
        return value

    def array(self, entries: int, value: LuaTable | None = None) -> LuaTable:
        if value is None:
            value = LuaTable()
            self.tables.append(value)
        for i in range(1, entries + 1):
            _set(value, i, self.obj())
        return value

    def mixed(self, array_count: int, map_count: int) -> LuaTable:
        value = LuaTable()
        self.tables.append(value)
        self.array(array_count, value)
        self.table(map_count, value)
        return value

    def ref(self, refs: list, n: int):
        i = self.int(n)
        if not 1 <= i <= len(refs):
            raise AuraError("cannot deserialize: bad reference")
        return refs[i - 1]

    def obj(self):
        self.count += 1
        if self.count > MAX_OBJECTS:
            raise AuraError("too many values in the string")
        self.depth += 1
        if self.depth > MAX_DEPTH:
            raise AuraError("tables nested too deep")
        try:
            return self._obj()
        finally:
            self.depth -= 1

    def _obj(self):
        v = self.int(1)
        if v % 2 == 1:
            return (v - 1) // 2
        if v % 4 == 2:
            typ = (v - 2) // 4
            count, typ = typ // 4, typ % 4
            if typ == 0:
                return self.string(count)
            if typ == 1:
                return self.table(count)
            if typ == 2:
                return self.array(count)
            return self.mixed(count % 4 + 1, count // 4 + 1)
        if v % 8 == 4:
            packed = self.int(1) * 256 + v
            return -((packed - 12) // 16) if v % 16 == 12 else (packed - 4) // 16
        typ = v // 8
        if typ == 0:
            return None
        if 1 <= typ <= 8:
            size = (2, 3, 4, 7)[(typ - 1) // 2]
            n = self.int(size)
            return -n if typ % 2 == 0 else n
        if typ == 9:
            return _float(self.bytes(8))
        if typ in (10, 11):
            f = _lua_number(self.bytes(self.int(1)).decode("latin-1"))
            return -f if typ == 11 else f
        if typ == 12:
            return True
        if typ == 13:
            return False
        if typ in (14, 15, 16):
            return self.string(self.int((1, 2, 3)[typ - 14]))
        if typ in (17, 18, 19):
            return self.table(self.int((1, 2, 3)[typ - 17]))
        if typ in (20, 21, 22):
            return self.array(self.int((1, 2, 3)[typ - 20]))
        if typ in (23, 24, 25):
            size = (1, 2, 3)[typ - 23]
            a = self.int(size)
            b = self.int(size)
            return self.mixed(a, b)
        if typ in (26, 27, 28):
            return self.ref(self.strings, (1, 2, 3)[typ - 26])
        if typ in (29, 30, 31):
            return self.ref(self.tables, (1, 2, 3)[typ - 29])
        raise AuraError("cannot deserialize: unknown type")


def _float(b: bytes) -> float:
    return struct.unpack(">d", b)[0]


def _set(t: LuaTable, k, v) -> None:
    if k is None or (isinstance(k, float) and math.isnan(k)):
        raise AuraError("cannot deserialize: bad table key")
    if isinstance(k, bool):
        k = LUA_TRUE if k else LUA_FALSE
    elif isinstance(k, float) and k.is_integer():
        k = int(k)  # Lua: t[1.0] is t[1]
    if v is None:
        t.pop(k, None)
    else:
        t[k] = v


def deserialize_libserialize(data: bytes) -> list:
    r = _LSReader(data)
    version = r.int(1)
    if version > 2:
        raise AuraError("cannot deserialize: unknown LibSerialize version")
    out = []
    while r.p < len(r.d):
        out.append(r.obj())
    return out


# --------------------------------------------------------------------------- AceSerializer-3.0


_ACE_TOKEN = re.compile(r"(\^.)([^^]*)")


def _ace_unescape(m: re.Match) -> str:
    c = m.group(0)[1]
    if c < "@":
        raise AuraError("cannot deserialize: bad escape")
    if c < "z":
        return chr(ord(c) - 64)
    out = {"z": "\x1e", "{": "\x7f", "|": "~", "}": "^"}.get(c)
    if out is None:
        raise AuraError("cannot deserialize: bad escape")
    return out


def deserialize_ace(text: str) -> list:
    text = re.sub(r"[\x00-\x1f\x7f ]", "", text)
    it = iter(_ACE_TOKEN.findall(text))
    first = next(it, None)
    if first is None or first[0] != "^1":
        raise AuraError("cannot deserialize: not AceSerializer data")
    counter = [0]

    def value(ctl: str, data: str, depth: int):
        counter[0] += 1
        if counter[0] > MAX_OBJECTS:
            raise AuraError("too many values in the string")
        if depth > MAX_DEPTH:
            raise AuraError("tables nested too deep")
        if ctl == "^S":
            # The data was read byte for byte (latin-1); Lua strings are UTF-8 bytes.
            return _str(re.sub(r"~.", _ace_unescape, data).encode("latin-1"))
        if ctl == "^N":
            if data in ("1.#INF", "inf"):
                return math.inf
            if data in ("-1.#INF", "-inf"):
                return -math.inf
            return _lua_number(data)
        if ctl == "^F":
            ctl2, e = next(it, (None, None))
            if ctl2 != "^f":
                raise AuraError("cannot deserialize: bad float")
            m, ex = _lua_number(data), _lua_number(e)
            if m == 0:
                return 0.0
            try:
                return m * 2.0**ex
            except OverflowError:
                return math.copysign(math.inf, m)
        if ctl == "^B":
            return True
        if ctl == "^b":
            return False
        if ctl == "^Z":
            return None
        if ctl == "^T":
            t = LuaTable()
            while True:
                kc, kd = next(it, (None, None))
                if kc is None:
                    raise AuraError("cannot deserialize: table not closed")
                if kc == "^t":
                    return t
                k = value(kc, kd, depth + 1)
                vc, vd = next(it, (None, None))
                if vc is None:
                    raise AuraError("cannot deserialize: table not closed")
                v = value(vc, vd, depth + 1)
                if k is None or v is None:
                    raise AuraError("cannot deserialize: bad table")
                _set(t, k, v)
        raise AuraError("cannot deserialize: bad control code")

    out = []
    for ctl, data in it:
        if ctl == "^^":
            return out
        out.append(value(ctl, data, 0))
    raise AuraError("cannot deserialize: AceSerializer end marker missing")


def _lua_number(s: str):
    if _HEX.fullmatch(s):
        return float(int(s, 16))
    if _DEC.fullmatch(s):
        return float(s)
    raise AuraError("cannot deserialize: bad number")


# --------------------------------------------------------------------------- import strings


@dataclass
class CodePiece:
    aura: str
    path: str  # where in the aura, e.g. triggers[1].trigger.custom
    code: str


@dataclass
class AuraExport:
    format: str  # "WA:2" or "WA:1"
    addon_version: str
    auras: list[str]  # ids, parent first
    code: list[CodePiece] = field(default_factory=list)
    chat: list[tuple[str, str, str]] = field(default_factory=list)  # (aura, path, "WHISPER → name")
    urls: list[str] = field(default_factory=list)


OTHER_FORMATS = {
    "!PLATER:": "Plater",
    "!E1!": "ElvUI",
    "!MDT": "Mythic Dungeon Tools",
}


def decode(text: str) -> tuple[str, LuaTable]:
    """Import string -> (format, transmit table)."""
    if len(text) > MAX_INPUT_CHARS:
        raise AuraError("the string is longer than 8 MB")
    s = text.strip(_LUA_SPACE)
    for prefix, name in OTHER_FORMATS.items():
        if s.startswith(prefix):
            raise AuraError(f"this looks like a {name} string; only WeakAuras strings are supported for now")
    m = re.match(r"^!WA:(\d+)!(.+)$", s, re.S)
    if m:
        version, body = int(m.group(1)), m.group(2)
    elif s.startswith("!"):
        version, body = 1, s[1:]
    else:
        version, body = 0, s
    if version == 0:
        # Pre-2018 strings. decodeB64 accepts anything, so a failure further on means "not an aura string".
        try:
            values = deserialize_ace(libcompress_decompress(decode_b64_v0(body)).decode("latin-1"))
        except AuraError as e:
            raise AuraError(V0_ERROR) from e
        if not values or not isinstance(values[0], LuaTable):
            raise AuraError(V0_ERROR)
        return ("WA:0", values[0])
    raw = decode_for_print(body)
    if raw is None:
        raise AuraError("cannot decode: the string has characters a WeakAuras export never has (was it cut or changed?)")
    data = inflate(raw)
    values = deserialize_libserialize(data) if version >= 2 else deserialize_ace(data.decode("latin-1"))
    if not values or not isinstance(values[0], LuaTable):
        raise AuraError("the string decodes, but not to a WeakAuras export")
    return (f"WA:{version}", values[0])


def _key_text(k) -> str:
    if isinstance(k, LuaBool):
        return f"[{k!r}]"
    if isinstance(k, (int, float)):
        return f"[{_num_text(k)}]"
    if isinstance(k, str):
        return f".{k}" if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", k) else "[" + _quote(k) + "]"
    return "[table]"


def _num_text(n) -> str:
    if isinstance(n, int):
        return str(n)
    if math.isinf(n):
        return "inf" if n > 0 else "-inf"
    return str(int(n)) if n.is_integer() else repr(n)  # e.g. 1.5, 1e-05 (the JavaScript port copies this)


def _quote(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def _sort_key(k):
    if isinstance(k, LuaBool):
        return (2, int(k.value), "")
    if isinstance(k, (int, float)):
        return (0, k, "")
    if isinstance(k, str):
        return (1, 0, k)
    return (3, 0, "")


def _is_code(key: str, value: str, parent: LuaTable) -> bool:
    if not value.strip():
        return False
    if key in CODE_KEYS:
        return True
    if key == "value" and parent.get("variable") == "customcheck":
        return True
    return bool(_GENERIC_KEY.search(key)) and bool(_CODE_LIKE.search(value))


def extract(fmt: str, transmit: LuaTable) -> AuraExport:
    root = transmit.get("d")
    if not isinstance(root, LuaTable):
        raise AuraError("the string decodes, but has no aura in it")
    displays = [root]
    children = transmit.get("c")
    if isinstance(children, LuaTable):
        displays += [children[k] for k in sorted((k for k in children if isinstance(k, int)), key=int) if isinstance(children[k], LuaTable)]
    s = transmit.get("s")
    out = AuraExport(fmt, s if isinstance(s, str) else "", [])
    seen_ids: dict[str, int] = {}
    for d in displays:
        name = d.get("id")
        name = name if isinstance(name, str) and name.strip() else "(no name)"
        if name in seen_ids:
            seen_ids[name] += 1
            name = f"{name} ({seen_ids[name]})"
        else:
            seen_ids[name] = 1
        out.auras.append(name)
        url = d.get("url")
        if isinstance(url, str) and url.strip() and url.strip() not in out.urls:
            out.urls.append(url.strip())
        _walk(d, "", name, out, set())
    return out


def _walk(t: LuaTable, path: str, aura: str, out: AuraExport, seen: set[int]) -> None:
    if id(t) in seen:
        return
    seen.add(id(t))
    if t.get("do_message") is True and t.get("message_type") in SEND_CHAT_TYPES:
        out.chat.append((aura, path.lstrip(".") or "(aura)", _chat_detail(t)))
    elif t.get("property") == "chat" and isinstance(t.get("value"), LuaTable):
        v = t["value"]
        if v.get("message_type") in SEND_CHAT_TYPES:
            out.chat.append((aura, (path + ".value").lstrip("."), _chat_detail(v)))
    for k in sorted(t.keys(), key=_sort_key):
        v = t[k]
        here = path + _key_text(k)
        if isinstance(v, LuaTable):
            _walk(v, here, aura, out, seen)
        elif isinstance(v, str) and isinstance(k, str) and _is_code(k, v, t):
            out.code.append(CodePiece(aura, here.lstrip("."), v))


def _chat_detail(t: LuaTable) -> str:
    kind = t.get("message_type")
    dest = t.get("message_dest")
    if kind == "WHISPER" and isinstance(dest, str) and dest.strip():
        return f"WHISPER → {dest.strip()[:40]}"  # code points, as the JavaScript port
    return str(kind)


def read(text: str) -> AuraExport:
    fmt, transmit = decode(text)
    return extract(fmt, transmit)
