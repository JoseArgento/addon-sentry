"""WeakAuras import strings: decoding (checked against the real Lua libraries when available) and scanning."""

import importlib.util
import math
import os
from pathlib import Path

import pytest

from addon_sentry import auras, engine

FIX = Path(__file__).parent / "fixtures" / "auras"
TOOLS = Path(__file__).resolve().parents[1] / "tools"


def load_tool():
    spec = importlib.util.spec_from_file_location("make_aura_fixtures", TOOLS / "make_aura_fixtures.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


LIBS = Path(os.environ.get("ADDON_SENTRY_LUA_LIBS", "/nonexistent"))


def fixture(name: str) -> str:
    return (FIX / f"{name}.txt").read_text(encoding="utf-8")


# WeakAuras' decodeB64 from Transmission.lua, copied as is (the pre-2018 format).
WA_DECODE_B64 = r"""
local string_char, bit_band, bit_lshift, bit_rshift = string.char, bit.band, bit.lshift, bit.rshift
local B64tobyte = {}
for i, c in ipairs({("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789()"):byte(1, -1)}) do B64tobyte[string.char(c)] = i - 1 end
local decodeB64Table = {}
function decodeB64(str)
  local bit8 = decodeB64Table;
  local decoded_size = 0;
  local ch;
  local i = 1;
  local bitfield_len = 0;
  local bitfield = 0;
  local l = #str;
  while true do
    if bitfield_len >= 8 then
      decoded_size = decoded_size + 1;
      bit8[decoded_size] = string_char(bit_band(bitfield, 255));
      bitfield = bit_rshift(bitfield, 8);
      bitfield_len = bitfield_len - 8;
    end
    ch = B64tobyte[str:sub(i, i)];
    bitfield = bitfield + bit_lshift(ch or 0, bitfield_len);
    bitfield_len = bitfield_len + 6;
    if i > l then
      break;
    end
    i = i + 1;
  end
  return table.concat(bit8, "", 1, decoded_size)
end
"""


def key(k):
    if isinstance(k, bool):
        return f"<{k}>"
    return int(k) if isinstance(k, float) and k.is_integer() else k


def plain(v, seen=None):
    """LuaTable -> comparable plain dicts (cycles become a marker)."""
    seen = seen or set()
    if isinstance(v, dict):
        if id(v) in seen:
            return "<cycle>"
        seen = seen | {id(v)}
        return {key(k.value if isinstance(k, auras.LuaBool) else k): plain(x, seen) for k, x in v.items()}
    if isinstance(v, float) and v.is_integer() and abs(v) < 2**53:
        return int(v)
    return v


@pytest.mark.skipif(not LIBS.is_dir(), reason="set ADDON_SENTRY_LUA_LIBS to a folder with LibDeflate/, LibSerialize/, Ace3/")
@pytest.mark.parametrize("name", ["clean", "mail_scam", "chat_and_blocked", "legacy_v1", "legacy_v0_lzw", "legacy_v0_huffman"])
def test_decoder_matches_the_real_libraries(name):
    lupa = pytest.importorskip("lupa.lua51")
    mk = load_tool()

    lua = lupa.LuaRuntime(unpack_returned_tuples=True)
    lua.execute(mk.PRELUDE)
    for rel in mk.LIB_FILES:
        lua.execute((LIBS / rel).read_text(encoding="utf-8"))
    decode = lua.execute(
        WA_DECODE_B64
        + """return function(s, v)
          local LD, LS, AS = LibStub("LibDeflate"), LibStub("LibSerialize"), LibStub("AceSerializer-3.0")
          if v == 0 then return select(2, AS:Deserialize(LibStub("LibCompress"):Decompress(decodeB64(s)))) end
          local body = s:match("^!WA:%d+!(.+)$") or s:sub(2)
          local raw = LD:DecompressDeflate(LD:DecodeForPrint(body))
          if v == 2 then return select(2, LS:Deserialize(raw)) end
          return select(2, AS:Deserialize(raw))
        end"""
    )
    s = fixture(name).strip()
    theirs = decode(s, 2 if s.startswith("!WA:2!") else 1 if s.startswith("!") else 0)

    tostring = lua.globals().tostring

    def to_py(v, seen=frozenset()):
        if lupa.lua_type(v) == "table":
            addr = tostring(v)  # "table: 0x...": the table's identity
            if addr in seen:
                return "<cycle>"
            seen = seen | {addr}
            return {key(k.decode() if isinstance(k, bytes) else k): to_py(x, seen) for k, x in v.items()}
        if isinstance(v, bytes):
            return v.decode("utf-8", "replace")
        if isinstance(v, float) and v.is_integer() and abs(v) < 2**53:
            return int(v)
        return v

    _, ours = auras.decode(s)
    assert plain(ours) == to_py(theirs)


def test_decode_clean_group():
    a = auras.read(fixture("clean"))
    assert a.format == "WA:2" and a.addon_version == "5.19.10"
    assert a.auras == ["Raid Cooldowns", "Rebirth CD", "Innervate CD"]
    assert a.urls == ["https://wago.io/AbCdEf123/4"]
    paths = [(c.aura, c.path) for c in a.code]
    assert ("Rebirth CD", "triggers[1].trigger.custom") in paths
    assert ("Rebirth CD", "triggers[1].trigger.customVariables") in paths
    assert ("Rebirth CD", "animation.start.alphaFunc") in paths
    assert ("Innervate CD", "customText") in paths and ("Raid Cooldowns", "customGrow") in paths
    assert a.chat == []  # PRINT goes to your own chat frame, it is not sent
    _, t = auras.decode(fixture("clean"))
    d = t["d"]
    assert d["xOffset"] == -300 and d["yOffset"] == 70000 and d["big"] == 2**40 and d["neg"] == -(2**40) and d["tiny"] == -12
    assert d["alpha"] == 0.25 and math.isclose(d["frac"], -0.1) and d["scale"] == 1.5
    assert d["color"] is d["borderColor"]  # shared table came through as a reference
    flags = d["flags"]
    assert flags[auras.LUA_TRUE] == "yes" and flags[1] == "one" and flags[2.5] == "half" and flags[auras.LUA_FALSE] == "no"
    assert ("Raid Cooldowns", "flags.customFunc") in paths
    odd = [p for a, p in paths if p.startswith("odd")]
    assert odd == [
        "odd[-7].custom",
        "odd[1e-05].custom",
        "odd[0.5].custom",
        "odd[3].custom",
        'odd["with space"].custom',
        "odd[true].custom",
    ]
    assert t["c"][2]["longnote"].startswith("This aura has a long description")


def test_decode_legacy_ace_serializer():
    a = auras.read(fixture("legacy_v1"))
    assert a.format == "WA:1" and a.addon_version == "2.17.6"
    _, t = auras.decode(fixture("legacy_v1"))
    assert t["d"]["name"] == "Combo ~ points ^ with \x01 escapes" and t["d"]["width"] == 200.5
    assert {c.path for c in a.code} == {"trigger.custom", "trigger.customDuration", "actions.start.custom"}


def test_cycles_do_not_hang():
    _, t = auras.decode(fixture("mail_scam"))
    assert t["d"]["loop"] is t["d"]


@pytest.mark.parametrize(
    "text, message",
    [
        ("hello", "not a WeakAuras import string"),
        ("!WA:2!abc$def", "cannot decode"),
        ("!WA:2!aaaaaaaa", "cannot decompress"),
        ("!PLATER:2!xyz", "Plater"),
        ("!E1!xyz", "ElvUI"),
    ],
)
def test_bad_strings(text, message):
    with pytest.raises(auras.AuraError, match=message):
        auras.read(text)


def test_cut_string():
    s = fixture("clean").strip()
    with pytest.raises(auras.AuraError):
        auras.read(s[: len(s) // 2])


def report(name):
    return engine.scan_aura(fixture(name)).to_dict("en")


def test_clean_aura_has_no_warning_signs():
    d = report("clean")
    assert d["verdict"]["level"] in ("info", "low"), d["findings"]
    assert d["stats"]["auras"] == 3 and d["stats"]["code_pieces"] == 13
    assert d["addons"][0]["title"] == "Raid Cooldowns"


def test_mail_scam_aura():
    d = report("mail_scam")
    ids = {f["id"] for f in d["findings"]}
    assert d["verdict"]["level"] == "high"
    assert {"AURA_BLOCKED", "BUILT_API_NAME", "INDIRECT_GLOBAL"} <= ids
    chat = next(c for c in d["capabilities"] if c["id"] == "chat")
    assert any(e["detail"] == "WHISPER → Goldbuyer" for e in chat["evidence"])
    money = next(c for c in d["capabilities"] if c["id"] == "money")
    ev = money["evidence"][0]
    assert ev["file"] == "Free Gold Tracker › actions.init.custom" and ev["line"] >= 1
    blocked = next(f for f in d["findings"] if f["id"] == "AURA_BLOCKED")
    assert {"SetSendMailMoney", "loadstring"} <= {e["detail"] for e in blocked["evidence"]}


def test_chat_and_blocked_aura():
    d = report("chat_and_blocked")
    ids = {f["id"] for f in d["findings"]}
    assert "EXFILTRATION" in ids  # reads the friend list and sends chat
    blocked = {e["detail"] for f in d["findings"] if f["id"] == "AURA_BLOCKED" for e in f["evidence"]}
    assert {"getfenv", "setfenv", "RunScript", "DEFAULT_CHAT_FRAME", "C_PetInfo.PetAbandon"} <= blocked
    chat = next(c for c in d["capabilities"] if c["id"] == "chat")
    assert any(e["detail"] == "GUILD" for e in chat["evidence"])


def test_legacy_aura_sabotage():
    d = report("legacy_v1")
    assert "SABOTAGE" in {f["id"] for f in d["findings"]}


def test_legacy_v0_strings():
    a = auras.read(fixture("legacy_v0_lzw"))
    assert a.format == "WA:0" and a.auras == ["Auction Helper"]
    d = engine.scan_aura(fixture("legacy_v0_lzw")).to_dict("en")
    assert any(c["id"] == "money" for c in d["capabilities"])
    a = auras.read(fixture("legacy_v0_huffman"))
    assert a.format == "WA:0" and {c.path for c in a.code} == {"trigger.custom", "trigger.customDuration"}


REAL_AURAS = Path(os.environ.get("ADDON_SENTRY_REAL_AURAS", "/nonexistent"))


@pytest.mark.skipif(not REAL_AURAS.is_dir(), reason="set ADDON_SENTRY_REAL_AURAS to a folder of exported .txt strings")
def test_real_strings_all_decode():
    files = sorted(REAL_AURAS.rglob("*.txt"))
    assert files
    for p in files:
        a = auras.read(p.read_text(encoding="utf-8", errors="replace"))
        assert a.auras, p
